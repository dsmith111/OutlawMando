// dstorage.dll proxy for Star Wars Outlaws (Snowdrop / DirectStorage 1.2.x, build 2305.1502)
//
// Purpose: intercept DirectStorage reads so we can OVERRIDE streamed assets (meshes,
// textures) that the Universal Snowdrop Modloader (version.dll) cannot touch -- those
// come through DirectStorage, not the CreateFile hook.
//
// PHASE 0 (this file): instrumentation only. Forward every real call unchanged, but log
//   - Factory::OpenFile(path)        -> maps an IDStorageFile* handle to an archive path
//   - Queue::EnqueueRequest(req)     -> {file handle, offset, size, compression, dest, name}
// so we can identify the exact read that streams the Boba helmet mesh. Phase 1 adds a
// memory-source substitution at the marked SUBSTITUTION HOOK below.
//
// Coexists with version.dll: different proxy target (dstorage.dll vs version.dll), no clash.
// Install: rename game's dstorage.dll -> dstorage_real.dll, drop this build in as dstorage.dll.

#include <windows.h>
#include <unknwn.h>
#include <cstdio>
#include <cstdint>
#include <cstddef>

// ---------------------------------------------------------------------------
// DirectStorage ABI (hand-mirrored from dstorage.h 1.2.3; offsets static_asserted)
// ---------------------------------------------------------------------------
#pragma pack(push, 8)
struct DS_OPTIONS {              // DSTORAGE_REQUEST_OPTIONS
    uint8_t  CompressionFormat;  // +0   0=NONE 1=GDEFLATE 0x80=custom
    uint8_t  Reserved1[7];       // +1
    uint64_t TypeBits;           // +8   bit0=SourceType(0=file,1=mem); bits1..7=DestType
};
static_assert(sizeof(DS_OPTIONS) == 16, "DS_OPTIONS");

struct DS_SOURCE_FILE   { void* Source; uint64_t Offset; uint32_t Size; };
struct DS_SOURCE_MEMORY { const void* Source; uint32_t Size; };
union DS_SOURCE {
    DS_SOURCE_MEMORY Memory;
    DS_SOURCE_FILE   File;
    uint8_t          _pad[24];
};
static_assert(sizeof(DS_SOURCE) == 24, "DS_SOURCE");

struct DSTORAGE_REQUEST {
    DS_OPTIONS  Options;          // +0
    DS_SOURCE   Source;           // +16
    uint8_t     Destination[40];  // +40 opaque (union sized by d3d12 dest types)
    uint32_t    UncompressedSize; // +80
    uint32_t    _pad0;            // +84
    uint64_t    CancellationTag;  // +88
    const char* Name;             // +96
};
static_assert(offsetof(DSTORAGE_REQUEST, Source) == 16, "Source@16");
static_assert(offsetof(DSTORAGE_REQUEST, Destination) == 40, "Dest@40");
static_assert(offsetof(DSTORAGE_REQUEST, UncompressedSize) == 80, "UCS@80");
static_assert(offsetof(DSTORAGE_REQUEST, CancellationTag) == 88, "Tag@88");
static_assert(offsetof(DSTORAGE_REQUEST, Name) == 96, "Name@96");
static_assert(sizeof(DSTORAGE_REQUEST) == 104, "DSTORAGE_REQUEST");
#pragma pack(pop)

// Interface vtables (mirrored order from dstorage.h). We inherit IUnknown so the
// first three slots (QI/AddRef/Release) are exact, then methods follow in order.
struct IDStorageQueueP : public IUnknown {
    virtual void    STDMETHODCALLTYPE EnqueueRequest(const DSTORAGE_REQUEST*) = 0;
    virtual void    STDMETHODCALLTYPE EnqueueStatus(void*, UINT32) = 0;
    virtual void    STDMETHODCALLTYPE EnqueueSignal(void*, UINT64) = 0;
    virtual void    STDMETHODCALLTYPE Submit() = 0;
    virtual void    STDMETHODCALLTYPE CancelRequestsWithTag(UINT64, UINT64) = 0;
    virtual void    STDMETHODCALLTYPE Close() = 0;
    virtual HANDLE  STDMETHODCALLTYPE GetErrorEvent() = 0;
    virtual void    STDMETHODCALLTYPE RetrieveErrorRecord(void*) = 0;
    virtual void    STDMETHODCALLTYPE Query(void*) = 0;
    virtual void    STDMETHODCALLTYPE EnqueueSetEvent(HANDLE) = 0;          // Queue1
    virtual UINT32  STDMETHODCALLTYPE GetCompressionSupport(UINT32) = 0;    // Queue2
};
struct IDStorageFactoryP : public IUnknown {
    virtual HRESULT STDMETHODCALLTYPE CreateQueue(const void*, REFIID, void**) = 0;
    virtual HRESULT STDMETHODCALLTYPE OpenFile(const wchar_t*, REFIID, void**) = 0;
    virtual HRESULT STDMETHODCALLTYPE CreateStatusArray(UINT32, const char*, REFIID, void**) = 0;
    virtual void    STDMETHODCALLTYPE SetDebugFlags(UINT32) = 0;
    virtual HRESULT STDMETHODCALLTYPE SetStagingBufferSize(UINT32) = 0;
};

static const GUID IID_IUnknown_       = {0x00000000,0x0000,0x0000,{0xC0,0,0,0,0,0,0,0x46}};
static const GUID IID_IDStorageFactory= {0x6924ea0c,0xc3cd,0x4826,{0xb1,0x0a,0xf6,0x4f,0x4e,0xd9,0x27,0xc1}};
static const GUID IID_IDStorageQueue  = {0xcfdbd83f,0x9e06,0x4fda,{0x8e,0xa5,0x69,0x04,0x21,0x37,0xf4,0x9b}};
static const GUID IID_IDStorageQueue1 = {0xdd2f482c,0x5eff,0x41e8,{0x9c,0x9e,0xd2,0x37,0x4b,0x27,0x81,0x28}};
static const GUID IID_IDStorageQueue2 = {0xb1c9d643,0x3a49,0x44a2,{0xb4,0x6f,0x65,0x36,0x49,0x47,0x0d,0x18}};

// ---------------------------------------------------------------------------
// Globals + real-DLL binding (lazy; never LoadLibrary inside DllMain)
// ---------------------------------------------------------------------------
typedef HRESULT (WINAPI *pfn_GetFactory)(REFIID, void**);
typedef HRESULT (WINAPI *pfn_SetConfig)(const void*);
typedef HRESULT (WINAPI *pfn_CreateCodec)(int, unsigned, REFIID, void**);

static HINSTANCE     g_self          = nullptr;
static HMODULE       g_real          = nullptr;
static pfn_GetFactory real_GetFactory = nullptr;
static pfn_SetConfig  real_SetConfig  = nullptr;
static pfn_SetConfig  real_SetConfig1 = nullptr;
static pfn_CreateCodec real_CreateCodec = nullptr;
static CRITICAL_SECTION g_cs;
static bool          g_inited       = false;
static FILE*         g_log          = nullptr;
static long          g_seq          = 0;
static long          g_logged       = 0;
static const long    LOG_CAP        = 1500000;   // bound the log; keep forwarding after
static char          g_dir[MAX_PATH]= {0};       // module directory (utf8-ish ascii)

static void log_line(const char* fmt, ...) {
    if (!g_log) return;
    va_list ap; va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);
    fputc('\n', g_log);
}

static void EnsureInit() {
    if (g_inited) return;
    EnterCriticalSection(&g_cs);
    if (!g_inited) {
        wchar_t path[MAX_PATH]; GetModuleFileNameW(g_self, path, MAX_PATH);
        // strip filename
        int n = (int)wcslen(path); while (n > 0 && path[n-1] != L'\\' && path[n-1] != L'/') n--;
        path[n] = 0;
        WideCharToMultiByte(CP_UTF8, 0, path, -1, g_dir, MAX_PATH, nullptr, nullptr);
        wchar_t realdll[MAX_PATH]; wcscpy(realdll, path); wcscat(realdll, L"dstorage_real.dll");
        g_real = LoadLibraryW(realdll);
        if (g_real) {
            real_GetFactory  = (pfn_GetFactory)GetProcAddress(g_real, "DStorageGetFactory");
            real_SetConfig   = (pfn_SetConfig)GetProcAddress(g_real, "DStorageSetConfiguration");
            real_SetConfig1  = (pfn_SetConfig)GetProcAddress(g_real, "DStorageSetConfiguration1");
            real_CreateCodec = (pfn_CreateCodec)GetProcAddress(g_real, "DStorageCreateCompressionCodec");
        }
        char logpath[MAX_PATH]; snprintf(logpath, sizeof(logpath), "%sdstorage_proxy.log", g_dir);
        g_log = fopen(logpath, "wb");
        setvbuf(g_log, nullptr, _IONBF, 0);   // unbuffered: survive hard process exit
        log_line("# dstorage proxy up. real=%p GetFactory=%p SetCfg=%p SetCfg1=%p Codec=%p",
                 (void*)g_real, (void*)real_GetFactory, (void*)real_SetConfig,
                 (void*)real_SetConfig1, (void*)real_CreateCodec);
        // Self-test: can the renamed real runtime produce a factory at all?
        if (real_GetFactory) {
            void* tf = nullptr;
            HRESULT thr = real_GetFactory(IID_IDStorageFactory, &tf);
            log_line("# selftest real GetFactory -> hr=0x%08lX factory=%p", (unsigned long)thr, tf);
            if (tf) ((IUnknown*)tf)->Release();
        }
        fflush(g_log);
        g_inited = true;
    }
    LeaveCriticalSection(&g_cs);
}

static inline bool IsIID(REFIID a, const GUID& b) { return IsEqualGUID(a, b) != 0; }

// ---------------------------------------------------------------------------
// Queue wrapper: logs EnqueueRequest, forwards everything else.
// ---------------------------------------------------------------------------
class QueueWrapper : public IDStorageQueueP {
    IDStorageQueueP* r;
    LONG ref;
public:
    QueueWrapper(IDStorageQueueP* real) : r(real), ref(1) {}

    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (IsIID(riid, IID_IUnknown_) || IsIID(riid, IID_IDStorageQueue) ||
            IsIID(riid, IID_IDStorageQueue1) || IsIID(riid, IID_IDStorageQueue2)) {
            *ppv = static_cast<IDStorageQueueP*>(this); AddRef(); return S_OK;
        }
        return r->QueryInterface(riid, ppv);
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&ref); }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG c = InterlockedDecrement(&ref);
        if (c == 0) { r->Release(); delete this; }
        return c;
    }

    void STDMETHODCALLTYPE EnqueueRequest(const DSTORAGE_REQUEST* req) override {
        if (req && g_log && g_logged < LOG_CAP) {
            long seq = InterlockedIncrement(&g_seq);
            unsigned comp = req->Options.CompressionFormat;
            unsigned src  = (unsigned)(req->Options.TypeBits & 1ull);
            unsigned dst  = (unsigned)((req->Options.TypeBits >> 1) & 0x7Full);
            char nm[160]; nm[0] = 0;
            const char* rn = req->Name;
            if (rn && (uintptr_t)rn > 0x10000) { // bounded copy of game-owned debug string
                int i = 0; for (; i < 156 && rn[i]; ++i) nm[i] = rn[i];
                nm[i] = 0;
            }
            EnterCriticalSection(&g_cs);
            if (g_logged < LOG_CAP) {
                if (src == 0)
                    log_line("R %ld F file=%p off=%llu sz=%u comp=%u dst=%u ucs=%u name=%s",
                             seq, req->Source.File.Source,
                             (unsigned long long)req->Source.File.Offset,
                             req->Source.File.Size, comp, dst, req->UncompressedSize, nm);
                else
                    log_line("R %ld M mem=%p sz=%u comp=%u dst=%u ucs=%u name=%s",
                             seq, req->Source.Memory.Source, req->Source.Memory.Size,
                             comp, dst, req->UncompressedSize, nm);
                ++g_logged;
            }
            LeaveCriticalSection(&g_cs);
        }
        // ===== SUBSTITUTION HOOK (Phase 1): if req matches a target, build a modified
        // copy with Source=Memory/CompressionFormat=NONE pointing at our replacement,
        // then r->EnqueueRequest(&copy); return. For now: pass through. =====
        r->EnqueueRequest(req);
    }

    void   STDMETHODCALLTYPE EnqueueStatus(void* a, UINT32 b) override { r->EnqueueStatus(a, b); }
    void   STDMETHODCALLTYPE EnqueueSignal(void* a, UINT64 b) override { r->EnqueueSignal(a, b); }
    void   STDMETHODCALLTYPE Submit() override { r->Submit(); }
    void   STDMETHODCALLTYPE CancelRequestsWithTag(UINT64 a, UINT64 b) override { r->CancelRequestsWithTag(a, b); }
    void   STDMETHODCALLTYPE Close() override { r->Close(); }
    HANDLE STDMETHODCALLTYPE GetErrorEvent() override { return r->GetErrorEvent(); }
    void   STDMETHODCALLTYPE RetrieveErrorRecord(void* a) override { r->RetrieveErrorRecord(a); }
    void   STDMETHODCALLTYPE Query(void* a) override { r->Query(a); }
    void   STDMETHODCALLTYPE EnqueueSetEvent(HANDLE h) override { r->EnqueueSetEvent(h); }
    UINT32 STDMETHODCALLTYPE GetCompressionSupport(UINT32 f) override { return r->GetCompressionSupport(f); }
};

// ---------------------------------------------------------------------------
// Factory wrapper: wraps queues it creates, logs file opens, forwards the rest.
// ---------------------------------------------------------------------------
class FactoryWrapper : public IDStorageFactoryP {
    IDStorageFactoryP* r;
    LONG ref;
public:
    FactoryWrapper(IDStorageFactoryP* real) : r(real), ref(1) {}

    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (IsIID(riid, IID_IUnknown_) || IsIID(riid, IID_IDStorageFactory)) {
            *ppv = static_cast<IDStorageFactoryP*>(this); AddRef(); return S_OK;
        }
        return r->QueryInterface(riid, ppv);
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&ref); }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG c = InterlockedDecrement(&ref);
        if (c == 0) { r->Release(); delete this; }
        return c;
    }

    HRESULT STDMETHODCALLTYPE CreateQueue(const void* desc, REFIID riid, void** ppv) override {
        if (g_log && desc) {
            unsigned long long srcType = *(const unsigned long long*)desc; // SourceType @+0
            EnterCriticalSection(&g_cs);
            log_line("Q CreateQueue srcType=%llu (0=file,1=mem)", srcType);
            LeaveCriticalSection(&g_cs);
        }
        void* raw = nullptr;
        HRESULT hr = r->CreateQueue(desc, riid, &raw);
        if (SUCCEEDED(hr) && raw) {
            *ppv = static_cast<IDStorageQueueP*>(new QueueWrapper((IDStorageQueueP*)raw));
        } else {
            *ppv = raw;
        }
        return hr;
    }

    HRESULT STDMETHODCALLTYPE OpenFile(const wchar_t* path, REFIID riid, void** ppv) override {
        HRESULT hr = r->OpenFile(path, riid, ppv);
        if (SUCCEEDED(hr) && ppv && *ppv && g_log) {
            char u[MAX_PATH]; u[0] = 0;
            WideCharToMultiByte(CP_UTF8, 0, path, -1, u, MAX_PATH, nullptr, nullptr);
            EnterCriticalSection(&g_cs);
            log_line("O file=%p path=%s", *ppv, u);
            fflush(g_log);
            LeaveCriticalSection(&g_cs);
        }
        return hr;
    }

    HRESULT STDMETHODCALLTYPE CreateStatusArray(UINT32 c, const char* n, REFIID riid, void** ppv) override {
        return r->CreateStatusArray(c, n, riid, ppv);
    }
    void    STDMETHODCALLTYPE SetDebugFlags(UINT32 f) override { r->SetDebugFlags(f); }
    HRESULT STDMETHODCALLTYPE SetStagingBufferSize(UINT32 s) override { return r->SetStagingBufferSize(s); }
};

static FactoryWrapper* g_factoryWrapper = nullptr;

// ---------------------------------------------------------------------------
// Exported functions (undecorated). One intercepted, three forwarded.
// ---------------------------------------------------------------------------
extern "C" __declspec(dllexport) HRESULT WINAPI DStorageGetFactory(REFIID riid, void** ppv) {
    EnsureInit();
    if (!real_GetFactory) return E_FAIL;
    bool match = IsIID(riid, IID_IDStorageFactory) || IsIID(riid, IID_IUnknown_);
    EnterCriticalSection(&g_cs);
    log_line("# DStorageGetFactory called by game (iid-match=%d)", match ? 1 : 0);
    if (match) {
        if (!g_factoryWrapper) {
            void* rawFactory = nullptr;
            HRESULT hr = real_GetFactory(IID_IDStorageFactory, &rawFactory);
            log_line("# game GetFactory -> hr=0x%08lX factory=%p", (unsigned long)hr, rawFactory);
            if (FAILED(hr) || !rawFactory) { LeaveCriticalSection(&g_cs); return hr; }
            g_factoryWrapper = new FactoryWrapper((IDStorageFactoryP*)rawFactory);
            log_line("# wrapped factory real=%p wrapper=%p", rawFactory, (void*)g_factoryWrapper);
        }
        g_factoryWrapper->AddRef();
        *ppv = static_cast<IDStorageFactoryP*>(g_factoryWrapper);
        LeaveCriticalSection(&g_cs);
        return S_OK;
    }
    LeaveCriticalSection(&g_cs);
    return real_GetFactory(riid, ppv);
}

extern "C" __declspec(dllexport) HRESULT WINAPI DStorageSetConfiguration(const void* c) {
    EnsureInit();
    HRESULT hr = real_SetConfig ? real_SetConfig(c) : E_FAIL;
    if (g_log) { EnterCriticalSection(&g_cs); log_line("# SetConfiguration -> hr=0x%08lX", (unsigned long)hr); LeaveCriticalSection(&g_cs); }
    return hr;
}
extern "C" __declspec(dllexport) HRESULT WINAPI DStorageSetConfiguration1(const void* c) {
    EnsureInit();
    HRESULT hr = real_SetConfig1 ? real_SetConfig1(c) : E_FAIL;
    if (g_log) { EnterCriticalSection(&g_cs); log_line("# SetConfiguration1 -> hr=0x%08lX", (unsigned long)hr); LeaveCriticalSection(&g_cs); }
    return hr;
}
extern "C" __declspec(dllexport) HRESULT WINAPI DStorageCreateCompressionCodec(int fmt, unsigned threads, REFIID riid, void** ppv) {
    EnsureInit();
    if (g_log) { EnterCriticalSection(&g_cs); log_line("# CreateCompressionCodec fmt=%d threads=%u", fmt, threads); LeaveCriticalSection(&g_cs); }
    return real_CreateCodec ? real_CreateCodec(fmt, threads, riid, ppv) : E_FAIL;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_self = h;
        DisableThreadLibraryCalls(h);
        InitializeCriticalSection(&g_cs);
    } else if (reason == DLL_PROCESS_DETACH) {
        if (g_log) { log_line("# detach: seq=%ld logged=%ld", g_seq, g_logged); fflush(g_log); }
    }
    return TRUE;
}
