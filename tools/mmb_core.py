# headless shims for SWOutlawsMeshTool parser (no Blender)
import sys, types, math
from struct import unpack, pack
import numpy as np
class Matrix:
    def __init__(self, rows=None): self.rows=rows
    def inverted(self): return self
class Euler:
    def __init__(self,*a,**k): pass
class Vector:
    def __init__(self, v=(0,0,0)): self.v=tuple(v)
_bpy=types.ModuleType("bpy")
class _NS: 
    def __init__(self,**k): self.__dict__.update(k)
_bpy.context=_NS(scene=_NS(SWOMT=_NS(AssetPath="")))
sys.modules["bpy"]=_bpy
sys.modules["bmesh"]=types.ModuleType("bmesh")

class ByteReader:
    @staticmethod
    def int8(f):
        b = f.read(1)
        i = unpack('<b', b)[0]
        return i
    @staticmethod
    def bool(f):
        b = f.read(1)
        i = unpack('<b', b)[0]
        if i == 0:
            return False
        elif i == 1:
            return True
        else:
            raise Exception("Byte at {v} wasn't a boolean".format(v=f.tell()))
    @staticmethod
    def uint8(f):
        b = f.read(1)
        i = unpack('<B', b)[0]
        return i
    @staticmethod
    def int16(f):
        return unpack('<h', f.read(2))[0]
    @staticmethod
    def uint16(f):
        b = f.read(2)
        i = unpack('<H', b)[0]
        return i
    @staticmethod
    def hash(f):
        b = f.read(8)
        return b
    @staticmethod
    def guid(f):
        return f.read(16)
    @staticmethod
    def int32(f):
        b = f.read(4)
        i = unpack('<i',b)[0]
        return i
    @staticmethod
    def uint32(f):
        b = f.read(4)
        i = unpack('<I',b)[0]
        return i
    @staticmethod
    def uint64(f):
        b = f.read(8)
        i = unpack('<Q',b)[0]
        return i
    @staticmethod
    def int64(f):
        b = f.read(8)
        i = unpack('<q', b)[0]
        return i
    @staticmethod
    def string(f,length):
        b = f.read(length)
        return "".join(chr(x) for x in b)
    @staticmethod
    def name(f):
        return br.string(f,br.uint16(f))
    @staticmethod
    def path(f):
        b = f.read(4)
        length = unpack('<i', b)[0]
        b = f.read(length)
        return "".join(chr(x) for x in b)
    @staticmethod
    def hashtext(f):
        b = f.read(4)
        length = unpack('<i', b)[0]
        f.seek(4,1)
        b = f.read(length)
        return "".join(chr(x) for x in b)
    @staticmethod
    def float(f):
        b = f.read(4)
        fl = unpack('<f',b)[0]
        return fl
    @staticmethod
    def vector3(f):
        b = f.read(12)
        return unpack('<fff', b)
    @staticmethod
    def dvector3(f):
        #double vector 3
        b = f.read(24)
        return unpack('<ddd', b)
    @staticmethod
    def vector4(f):
        b = f.read(16)
        return unpack('<ffff', b)
    @staticmethod
    def int16_norm(f):
        i = unpack('<H', f.read(2))[0]
        v = i ^ 2**15
        v -= 2**15
        v /= 2**15 - 1
        return v
    @staticmethod
    def uint16_norm(f):
        uint16 = unpack('<H', f.read(2))[0]
        return uint16 / ((2 ** 16) - 1)
    @staticmethod
    def uint8_norm(f):
        uint8 = unpack('<B', f.read(1))[0]
        maxint = (2 ** 8)-1
        return uint8 / maxint
    @staticmethod
    def int8_norm(f):
        int8 = unpack('<B', f.read(1))[0]
        v = int8 ^ 2**7
        v -= 2**7
        v /= 2**7 -1
        return v
    @staticmethod
    def X10Y10Z10W2_normalized(f):
        i = unpack('<I', f.read(4))[0]  # get 32bits of data

        x = i >> 0
        x = ((x & 0x3FF) ^ 512) - 512

        y = i >> 10
        y = ((y & 0x3FF) ^ 512) - 512

        z = i >> 20
        z = ((z & 0x3FF) ^ 512) - 512

        w = i >> 30
        w = w & 0x1

        vectorLength = math.sqrt(x ** 2 + y ** 2 + z ** 2)
        # # print(x,y,z)
        if vectorLength != 0:
            x /= vectorLength
            y /= vectorLength
            z /= vectorLength
        return [x, y, z, w]
    @staticmethod
    def matrix_4x4(f):
        row1 = []
        row2 = []
        row3 = []
        row4 = []
        for i in range(4):
            for c in range(4):
                value = br.float(f)
                if c == 0:
                    row1.append(value)
                if c == 1:
                    row2.append(value)
                if c == 2:
                    row3.append(value)
                if c == 3:
                    row4.append(value)
        # print(Matrix((row1,row2,row3,row4)))
        matrix = Matrix((row1, row2, row3, row4))#.inverted()
        return matrix
class BytePacker:
    @staticmethod
    def int8(v):
        return pack('<b', v)
    @staticmethod
    def uint8(v):
        return pack('<B', v)
    @staticmethod
    def uint8_norm(v):
        if 0.0 <= v <= 1.001:
            i = max(0,min(int(v * ((2 ** 8)-1)),255))
        else:
            raise Exception("Couldn't normalize value as uint8Norm, "
                            "it wasn't between 0.0 and 1.0. Unknown max value."
                            +str(v))
        return pack('<B', i)
    @staticmethod
    def int8_norm(v):
        if -1.001 <= v <= 1.001:
            i = max(-255, min(int(v * ((2 ** 7) - 1)), 255))
        else:
            raise Exception("Couldn't normalize value as uint8Norm, "
                            "it wasn't between -1.0 and 1.0. Unknown max value."
                            + str(v))
        return pack('<b', i)
    @staticmethod
    def int16(v):
        return pack('<h', v)
    @staticmethod
    def uint16(v):
        return pack('<H', v)
    @staticmethod
    def int16_norm(v):
        # print(v)
        if -1.0 <= v <= 1.0:
            # if v >= 0:
            #     v = int(abs(v) * (2 ** 15))
            # else:
            #     v = 2 ** 16 - int(abs(v) * (2 ** 15))
            v = max(min(int(v * (2 ** 15)),32767), -32768)
        else:
            raise Exception("Couldn't normalize value as int16Norm, it wasn't between -1.0 and 1.0. Unknown max value.")
        return pack('<h', v)
    @staticmethod
    def uint16_norm(v, exp=16, max_value=0xFFFF):
        if 0.0 <= v <= 1.0:
            i = max(0, min(int(round(v * ((2 ** exp) - 1))), max_value))
        else:
            raise Exception("Couldn't normalize value as uint16Norm, it wasn't between 0.0 and 1.0. Unknown max value. " + str(v))
        return pack('<H', i)
    @staticmethod
    def float16(v):
        f32 = np.float32(v)
        f16 = f32.astype(np.float16)
        b16 = f16.tobytes()
        return b16
    @staticmethod
    def int32(v):
        return pack('<i', v)
    @staticmethod
    def uint32(v):
        return pack('<I', v)
    @staticmethod
    def uint64(v):
        return pack('<Q', v)
    @staticmethod
    def int64(v):
        return pack('<q', v)
    @staticmethod
    def float(v):
        return pack('<f', v)
    @staticmethod
    def X10Y10Z10W2(x,y,z,w):
        if x >= 0:
            x = int(abs(x) * 2 ** 9)
        else:
            x = 2**10 - int(abs(x) * 2 ** 9)
        if y >= 0:
            y = int(abs(y) * 2 ** 9)
        else:
            y = 2**10 - int(abs(y) * 2 ** 9)
        if z >= 0:
            z = int(abs(z) * 2 ** 9)
        else:
            z = 2**10 - int(abs(z) * 2 ** 9)


        w = int(w)


        x = (abs(x) & 0x3FF)
        y = (abs(y) & 0x3FF) << 10
        z = (abs(z) & 0x3FF) << 20
        w = (abs(w) & 0x3) << 30

        v = x | y | z | w
        return pack("<I", v)
    @staticmethod
    def matrix_4x4(matrix:Matrix):
        out_matrix = b''
        for i in range(4):
            for c in range(4):
                if abs(matrix[c][i]) < 0.0001:
                    out_matrix += bp.float(0.0)
                else:
                    out_matrix += bp.float(matrix[c][i])
        return out_matrix

br = ByteReader
bp = BytePacker

def CopyFile(read,write,offset,size,buffer_size=500000):
    read.seek(offset)
    chunks = size // buffer_size
    for o in range(chunks):
        write.write(read.read(buffer_size))
    write.write(read.read(size%buffer_size))
def get_merged_mmb(mmb):
    files = []
    if str(mmb).endswith("mmb"):
        files.append(mmb)
    else:
        i = 0
        while True:
            current_file = f"{str(mmb)[:-1]}{i}"
            if os.path.isfile(current_file):
                files.append(current_file)
                i += 1
            else:
                break

    f = io.BytesIO()
    for file_dir in files:
        with open(file_dir, 'rb') as file:
            f.write(file.read())
    return f

class Asset:
    def __init__(self):
        self.magic = ""
        self.version = 0
        self.size = 0
    def parse(self,f):
        self.magic = br.string(f,3)
        self.version = br.uint8(f)
        self.size = br.uint32(f)
        f.seek(4,1)
    def write(self,f):
        f.seek(4)
        f.write(bp.uint32(self.size))

class SkeletalMeshAsset(Asset):
    class Mesh:
        class LOD:
            def __init__(self, parent_mesh,index):
                self.start_offset = 0
                self.parent_mesh:SkeletalMeshAsset.Mesh = parent_mesh
                self.index = index
                self.vertex_count = 0
                self.index_count = 0
                self.size_a = 0
                self.vertex_data_offset_a = 0
                self.vertex_data_offset_b = 0
                self.face_block_offset = 0
                self.data_offset = 0
                self.data_size = 0
                self.lod_screen_size = 0.0
                self.data_x_offset = 0
                self.data_x_size = 0
                self.data_y_offset = 0
                self.data_y_size = 0
                self.local_vertex_stride = 0
                self.lod_info_type = 0
                self.is_header_lod = False
                self.vertex_end_bytes = None
                self.normals_end_bytes = None
                self.faces_end_bytes = None

            def parse(self, f, lod_info_type = 0):
                self.lod_info_type = lod_info_type
                self.start_offset = f.tell()
                self.vertex_count = br.uint32(f)
                self.index_count = br.uint32(f)
                self.size_a = br.uint32(f) # seems to be face_block_offset divided by 2
                self.vertex_data_offset_a = br.uint32(f)
                self.vertex_data_offset_b = br.uint32(f)
                self.face_block_offset = br.uint32(f)
                self.data_offset = br.uint32(f)
                self.data_size = br.uint32(f)
                self.lod_screen_size = br.float(f)  # not confirmed screen size
                if self.vertex_count > 0:
                    if lod_info_type == 0:
                        pass
                    elif lod_info_type == 12:
                        unk1 = br.uint32(f)
                        self.data_x_offset = br.uint32(f)
                        self.data_x_size = br.uint32(f)
                        unk2 = br.uint32(f)
                        self.data_y_offset = br.uint32(f)
                        self.data_y_size = br.uint32(f)
                        self.local_vertex_stride = int(self.data_y_size / self.vertex_count)
                        print("New Vertex Stride = ", self.local_vertex_stride)
                    else:
                        f.seek(28,1)
                if self.data_offset < self.parent_mesh.parent_sk_mesh.size:
                    self.is_header_lod = True
                    print("Lod ", self.index, "is in header.")

            def write(self, f):
                f.seek(self.start_offset)
                f.write(bp.uint32(self.vertex_count))
                # print("Written vertex count: ",self.vertex_count)
                f.write(bp.uint32(self.index_count))
                f.write(bp.uint32(int(self.face_block_offset / 2)))
                f.write(bp.uint32(self.vertex_data_offset_a))
                f.write(bp.uint32(self.vertex_data_offset_b))
                f.write(bp.uint32(self.face_block_offset))
                f.write(bp.uint32(self.data_offset))
                f.write(bp.uint32(self.data_size))
                f.write(bp.float(self.lod_screen_size))
            def write_data_offset(self,f):
                f.seek(self.start_offset + 24)
                f.write(bp.uint32(self.data_offset))

            def gather_extra_bytes(self,f):
                offset = f.tell()
                f.seek(self.data_offset)
                real_vertex_size = self.vertex_count * self.parent_mesh.vertex_stride
                if self.vertex_data_offset_a == self.vertex_data_offset_b:
                    extra_bytes_size = self.face_block_offset - self.vertex_data_offset_a - real_vertex_size
                else:
                    extra_bytes_size = self.vertex_data_offset_b - self.vertex_data_offset_a - real_vertex_size
                f.seek(real_vertex_size, 1)
                # print(f.tell())
                if extra_bytes_size > 0:
                    self.vertex_end_bytes = f.read(extra_bytes_size)
                else:
                    print("No Extra Vertex bytes: ", extra_bytes_size)
                # print("Vertex Extra Bytes:",self.vertex_end_bytes)

                if not self.vertex_data_offset_a == self.vertex_data_offset_b:
                    real_normals_size = self.vertex_count * self.parent_mesh.normals_stride
                    extra_bytes_size = self.face_block_offset - self.vertex_data_offset_b - real_normals_size
                    f.seek(real_normals_size, 1)
                    # print(f.tell())
                    if extra_bytes_size > 0:
                        self.normals_end_bytes = f.read(extra_bytes_size)
                    else:
                        print("No Extra Normals bytes: ", extra_bytes_size)
                    # print("Normal Extra Bytes:",self.normals_end_bytes)

                real_face_size = self.index_count * 2
                size_without_face = self.face_block_offset - self.vertex_data_offset_a
                extra_bytes_size = self.data_size - size_without_face - real_face_size
                f.seek(real_face_size, 1)
                # print(f.tell())
                if extra_bytes_size > 0:
                    self.faces_end_bytes = f.read(extra_bytes_size)
                # print("Face Extra Bytes:",self.faces_end_bytes)
                else:
                    print("No Extra Face bytes: ", extra_bytes_size)
                f.seek(offset)

            def get_vertex_positions(self,raw_mesh_file):
                vertices = []
                if self.local_vertex_stride > 0:
                    stride = self.local_vertex_stride
                else:
                    stride = self.parent_mesh.vertex_stride
                print(stride)
                if self.data_y_offset != 0:
                    print("Vertex Data is in mmb file.")
                    SWOMT = bpy.context.scene.SWOMT
                    file = SWOMT.AssetPath
                    f = open(file,"rb")
                    print(self.data_y_offset)
                    f.seek(self.data_y_offset)
                else:
                    f = raw_mesh_file
                    f.seek(self.vertex_data_offset_a)
                pos = (0.0,0.0,0.0)
                for v in range(self.vertex_count):
                    stride_start = f.tell()
                    if self.parent_mesh.position_type == 0:
                        x = br.int16_norm(f)
                        y = br.int16_norm(f)
                        z = br.int16_norm(f)
                        w = br.int16(f)
                        pos = (x*w,y*w,z*w)
                    elif self.parent_mesh.position_type == 1:
                        x = br.float(f)
                        y = br.float(f)
                        z = br.float(f)
                        pos = (x,y,z)

                    f.seek(stride_start + stride)
                    if v  == 0:
                        print(f.tell())
                    vertices.append(pos)
                return vertices

            def get_bone_weights(self, raw_mesh_file):
                """
                Read bone weights while preserving fixed slot alignment.

                The vertex buffer may physically store more weight/index slots than the
                declared logical weight count. Always read the full physical layout so
                weight bytes and index bytes remain aligned.
                """
                bone_weights = []
                if self.lod_info_type == 12:
                    stride = self.local_vertex_stride
                    SWOMT = bpy.context.scene.SWOMT
                    file = SWOMT.AssetPath
                    f = open(file, "rb")
                    f.seek(self.data_y_offset)
                else:
                    stride = self.parent_mesh.vertex_stride
                    f = raw_mesh_file
                    f.seek(self.vertex_data_offset_a)

                pos_length = self.parent_mesh.get_vertex_position_length()
                layout = self.parent_mesh.get_vertex_weight_storage_layout()
                weight_type = layout['weight_type']
                index_type = layout['index_type']
                storage_weight_count = layout['count']

                if self.parent_mesh.is_rigid_single_binding_float3_layout():
                    print(
                        f"Rigid single-binding weight layout detected for "
                        f"{self.parent_mesh.name}_LOD{self.index}; "
                        f"assigning all vertices to mesh bone 0 with weight 1.0."
                    )
                    for v in range(self.vertex_count):
                        bone_weights.append({0: 1.0})
                    return bone_weights

                for v in range(self.vertex_count):
                    vertex_stride_start = f.tell()
                    f.seek(pos_length, 1)

                    weights = []
                    for w in range(storage_weight_count):
                        if weight_type == 'uint16_norm':
                            weights.append(br.uint16_norm(f))
                        else:
                            weights.append(br.uint8_norm(f))

                    indices = []
                    for i in range(storage_weight_count):
                        if index_type == 'uint16':
                            indices.append(br.uint16(f))
                        else:
                            indices.append(br.uint8(f))

                    iw = {}
                    for i in range(storage_weight_count):
                        if weights[i] > 0.0:
                            iw[indices[i]] = weights[i]

                    f.seek(vertex_stride_start + stride)
                    if v == 0:
                        print("Weight vertex info vvvvvvvvvvvvvv")
                        print(f.tell())
                        print(vertex_stride_start)
                        print(weight_type, storage_weight_count, index_type)
                        print(iw)
                    bone_weights.append(iw)
                return bone_weights
            def get_triangles(self,raw_mesh_file):
                """
                Seeks to Lod.face_block_offset and reads all triangle indices.
                :param raw_mesh_file: file that is exported by SkeletalMeshAsset.Mesh.extract_mesh_file()
                :return: a List of Tuples containing 3 vertex indices to form a triangle.
                """
                tris = []
                f = raw_mesh_file
                f.seek(self.face_block_offset)
                print(f.tell())
                tris_count = int(self.index_count/3)
                if self.vertex_count == self.index_count:
                    index_count = int(self.size_a / 4)
                    print(index_count, self.size_a)
                    tris_count = int(index_count/3)
                print("Triangles Count:",tris_count)
                for i in range(tris_count):
                        f1 = br.uint16(f)
                        f2 = br.uint16(f)
                        f3 = br.uint16(f)
                        tris.append((f1,f2,f3))
                return tris

            def get_normals_size(self):
                if self.parent_mesh.normal_type == 'int8_norm':
                    return 8
                else:
                    return 28

            def get_normals(self,raw_mesh_file):
                normals = []
                stride = self.parent_mesh.normals_stride
                f = raw_mesh_file
                f.seek(self.vertex_data_offset_b)
                v = Vector((0.0,0.0,1.0))
                for i in range(self.vertex_count):
                    stride_start = f.tell()
                    if self.parent_mesh.normal_type == "int8_norm":
                        x = br.int8_norm(f) *-1
                        y = br.int8_norm(f)
                        z = br.int8_norm(f)
                        w = br.int8(f)
                        v = Vector((x*w, y*w, z*w)).normalized()
                        v.negate()  # TODO not sure about this
                    elif self.parent_mesh.normal_type == "float":
                        x = br.float(f) *-1
                        y = br.float(f)
                        z = br.float(f)
                        v = Vector((x,y,z)).normalized()
                    f.seek(stride_start + stride)
                    normals.append(v)
                return normals

            def get_uvs(self,raw_mesh_file, index=0):
                """
                Seeks to Lod.vertex_data_offset_b and reads all UV data.
                :param raw_mesh_file: file that is exported by SkeletalMeshAsset.Mesh.extract_mesh_file()
                :return: a List of Tuples containing 2 floats as UV coordinates.
                """
                uvs = []
                color_count = self.parent_mesh.color_count
                f = raw_mesh_file
                print(f'Load Info Type: {self.lod_info_type}')
                if self.lod_info_type == 12:

                    stride = self.parent_mesh.vertex_stride
                    f.seek(self.vertex_data_offset_a)
                    for i in range(self.vertex_count):
                        stride_start = f.tell()
                        f.seek(4 * color_count, 1)
                        u = br.int16_norm(f)
                        v = br.int16_norm(f)
                        f.seek(stride_start + stride)
                        uvs.append((u,v))
                else:
                    stride = self.parent_mesh.normals_stride
                    f.seek(self.vertex_data_offset_b)
                    for i in range(self.vertex_count):
                        stride_start = f.tell()
                        f.seek(self.get_normals_size(), 1) #skip normals
                        f.seek(4 * color_count, 1) #skip color
                        f.seek(index * 4, 1)  # skip previous uv
                        if index == 1 and stride - (f.tell() - stride_start) == 8: #TODO this is guesswork
                            u = br.float(f)
                            v = br.float(f)
                        else:
                            u = br.int16_norm(f)
                            v = br.int16_norm(f)
                        f.seek(stride_start + stride)
                        uvs.append((u,v))
                return uvs

            def get_color(self,raw_mesh_file, index=0):
                """
               Seeks to Lod.vertex_data_offset_b and reads all Color data.
               :param raw_mesh_file: file that is exported by SkeletalMeshAsset.Mesh.extract_mesh_file()
               :return: a List of Tuples containing 4 floats as RGBA coordinates.
               """
                colors = []
                f = raw_mesh_file
                if self.lod_info_type == 12:
                    stride = self.parent_mesh.vertex_stride
                    f.seek(self.vertex_data_offset_a)
                    for i in range(self.vertex_count):
                        stride_start = f.tell()
                        f.seek(index * 4, 1) #skip previous color
                        r = br.uint8_norm(f)
                        g = br.uint8_norm(f)
                        b = br.uint8_norm(f)
                        a = br.uint8_norm(f)
                        f.seek(stride_start + stride)
                        colors.append((r,g,b,a))
                else:
                    stride = self.parent_mesh.normals_stride
                    f.seek(self.vertex_data_offset_b)
                    for i in range(self.vertex_count):
                        stride_start = f.tell()
                        f.seek(self.get_normals_size(), 1) #skip normals
                        f.seek(index * 4, 1) #skip previous color
                        r = br.uint8_norm(f)
                        g = br.uint8_norm(f)
                        b = br.uint8_norm(f)
                        a = br.uint8_norm(f)
                        f.seek(stride_start + stride)
                        colors.append((r,g,b,a))
                return colors

            def write_vertex_position(self,file,pos=(0.0,0.0,0.0),scale=2):
                """
                Writes a single vertex position into file at the current position and skips to the end of stride.
                :param file: file to write on
                :param pos: (x,y,z)
                :return:
                """
                f = file
                x = pos[0]
                y = pos[1]
                z = pos[2]
                if self.local_vertex_stride > 0:
                    stride = self.local_vertex_stride
                else:
                    stride = self.parent_mesh.vertex_stride
                stride_start = f.tell()
                if self.parent_mesh.position_type == 0:
                    f.write(bp.int16_norm(x / scale))
                    f.write(bp.int16_norm(y / scale))
                    f.write(bp.int16_norm(z / scale))
                    f.write(bp.int16(scale))
                elif self.parent_mesh.position_type == 1:
                    f.write(bp.float(x))
                    f.write(bp.float(y))
                    f.write(bp.float(z))
                f.seek(stride_start + stride)

        def __init__(self,parent_sk_mesh,index = 0):
            self.parent_sk_mesh:SkeletalMeshAsset = parent_sk_mesh
            if self.parent_sk_mesh.bone_count > 0xFF:
                self.vertex_weight_index_type = 'uint16' # 1: uint16
            else:
                self.vertex_weight_index_type = 'uint8'  # 0: uint8
            self.vertex_weight_type = 'uint8_norm'
            self.index = index
            self.name = ""
            self.lod_count_offset = 0
            self.binding_count_offset = 0
            self.binding_count = 0
            self.lod_count = 0
            self.lods = []
            self.weight_count = 0
            self.vertex_stride = 0
            self.normals_stride = 0

            self.mesh_bones = {}
            self.extra_bones = [] # bones that weren't in mesh_bones but are needed for mod mesh.
            self.real_bone_indices_to_mesh_bones = {}

            self.color_count = 0
            self.uv_count = 0
            self.normal_type = 'float' # 0:int8_norm 1:float
            self.position_type = 0 # 0:int16_norm 1:float
            self.end_bytes = None # bytes from the end of the last LOD to the end of the mesh section.
            self.mesh_file = None # BytesIO of reversed ordered LOD mesh data.

        def get_vertex_position_length(self):
            if self.position_type == 0:
                return 8
            elif self.position_type == 1:
                return 12
            return 12

        def is_rigid_single_binding_float3_layout(self):
            """Return True for rigid accessory meshes using float3 positions in a 16-byte stride."""
            return (self.vertex_stride == 16 and self.weight_count == 1 and
                    self.binding_count == 1 and self.normal_type == "float")

        def get_vertex_weight_storage_layout(self):
            """
            Return the physical weight/index layout implied by the vertex stride.

            Some meshes declare a logical weight count that is smaller than the
            physical number of weight/index slots stored in the vertex buffer. Some
            other meshes are ambiguous enough that the old heuristic guessed
            uint16_norm weights even though the physical stride matches packed
            uint8_norm weights plus uint8 indices.
            """
            if self.is_rigid_single_binding_float3_layout():
                return {
                    'count': 1,
                    'weight_type': 'rigid_single_binding',
                    'index_type': self.vertex_weight_index_type,
                    'weight_unit': 0,
                    'index_unit': 0,
                }

            index_type = self.vertex_weight_index_type
            index_unit = 2 if index_type == 'uint16' else 1
            pos_length = self.get_vertex_position_length()
            remaining = self.vertex_stride - pos_length

            # If the parser guessed uint16 weights from an odd 3-bytes-per-declared-slot
            # layout, also test the common packed uint8 weights + indices layout.
            alt_slot_size = 1 + index_unit
            if self.weight_count > 1 and remaining > 0 and alt_slot_size > 0 and remaining % alt_slot_size == 0:
                alt_capacity = remaining // alt_slot_size
                if self.vertex_weight_type == 'uint16_norm' and alt_capacity >= self.weight_count and alt_capacity <= 8:
                    print(f"Detected packed uint8 weight layout for {self.name}: declared/guessed {self.weight_count}x{self.vertex_weight_type}+{index_type}, stride fits {alt_capacity}xuint8_norm+{index_type}.")
                    return {'count': alt_capacity, 'weight_type': 'uint8_norm', 'index_type': index_type, 'weight_unit': 1, 'index_unit': index_unit}

            weight_type = self.vertex_weight_type
            weight_unit = 2 if weight_type == 'uint16_norm' else 1
            slot_size = weight_unit + index_unit
            count = self.weight_count
            if self.weight_count > 1 and remaining > 0 and slot_size > 0 and remaining % slot_size == 0:
                capacity = remaining // slot_size
                if capacity >= self.weight_count and capacity <= 8:
                    if capacity != self.weight_count:
                        print(f"Detected extra physical weight slots for {self.name}: declared weight_count={self.weight_count}, stride stores {capacity} slots.")
                    count = capacity
            return {'count': count, 'weight_type': weight_type, 'index_type': index_type, 'weight_unit': weight_unit, 'index_unit': index_unit}

        def get_vertex_weight_storage_count(self):
            return self.get_vertex_weight_storage_layout()['count']

        def get_vertex_weight_storage_type(self):
            return self.get_vertex_weight_storage_layout()['weight_type']

        def parse(self, f):
            mesh_start_offset = f.tell()
            self.name = br.name(f)
            print("\n" + "-" * 72)
            print(f"LOAD MESH START: {self.name}  (mesh_index={self.index})")
            print("-" * 72)
            print("Mesh Start Offset:", mesh_start_offset)
            f.seek(48, 1)  # some kind of matrix
            f.seek(1, 1)
            x_count = br.uint16(f)
            f.seek(4 * x_count, 1)
            if self.parent_sk_mesh.version != 17:
                y_count = br.uint16(f)
                f.seek(4 * y_count, 1)
            else:
                y_count = 0

            print("Binding Count Offset:", f.tell())
            self.binding_count_offset = f.tell()
            self.binding_count = br.uint16(f)
            for b in range(self.binding_count):
                matrix = br.matrix_4x4(f)
                bone_index = br.uint16(f)
                self.parent_sk_mesh.bones[bone_index].set_mesh_matrix(matrix)
                self.mesh_bones[bone_index] = matrix
                self.real_bone_indices_to_mesh_bones[bone_index] = b
                # print(bone_index, " = ", b)
            if self.parent_sk_mesh.version != 17:
                f.seek(2, 1)
            else:
                f.seek(1,1)
            flag_1, flag_2, flag_3 = 0, 0, 0
            if self.parent_sk_mesh.version != 17:
                if y_count > 0:
                    flag_1 = br.uint8(f)
                    flag_2 = br.uint8(f)
                    flag_3 = br.uint8(f)
            lod_info_type = br.uint16(f)
            self.lod_count_offset = f.tell()
            print("Lod Count Offset: ",self.lod_count_offset)
            self.lod_count = br.uint8(f)
            f.seek(4, 1)
            for l in range(self.lod_count):
                lod = self.LOD(self,l)
                lod.parse(f, lod_info_type)
                self.lods.append(lod)
            print("LOD Info End Offset:", f.tell())
            #this section could be wrong
            self.uv_count = br.uint8(f)
            f.seek(4*self.uv_count,1)
            self.color_count = br.uint8(f)
            f.seek(4*self.color_count,1)
            self.weight_count = br.uint32(f)
            count_c = br.uint8(f)
            f.seek(4*count_c,1)
            if lod_info_type == 12:
                f.seek(2,1)
            print("Vertex Stride Offset:", f.tell())
            self.vertex_stride = br.uint16(f)
            self.normals_stride = br.uint16(f)

            if lod_info_type == 12:
                if flag_3 == 1:
                    f.seek(14, 1)
                    pca_count = br.uint32(f)
                    print("PCA Count : ",pca_count)
                    for pca in range(pca_count):
                        pca_length = br.uint16(f)
                        f.seek(pca_length, 1)
                        f.seek(4, 1)
                else:
                    f.seek(18, 1)
            else:
                f.seek(20, 1)
            print("PCA End Offset:", f.tell())
            # Gather extra bytes at the end of each LOD's vertex/normal/face data.
            # Must be done after getting stride lengths.
            for l in self.lods:
                if l.vertex_count > 0:
                    l.gather_extra_bytes(f)

            # guessing the type of normal data int8 or floats
            possible_normal_length = self.normals_stride - (4 * self.uv_count) - (4 * self.color_count)
            if possible_normal_length > 16:
                self.normal_type = "float"
            else:
                self.normal_type = "int8_norm"

            # guessing the type of vertex position data int16 or floats

            if self.vertex_stride - 16 == 8 or self.vertex_stride - 8 == 8 or (self.vertex_stride == 12 and self.weight_count == 1):
                self.position_type = 0 #int16
                position_length = 8
            elif self.vertex_stride - 16 == 12 or self.vertex_stride - 8 == 12:
                self.position_type = 1 #float
                position_length = 12
            else:
                self.position_type = 1 #float
                position_length = 12
            # Rigid accessory/metal meshes can use a compact 16-byte vertex layout:
            # float3 position + 4 trailing bytes. With weight_count=1 and a single
            # mesh binding, stride-only heuristics can misclassify this as
            # int16_norm+scale and collapse the mesh in Blender.
            if self.is_rigid_single_binding_float3_layout():
                if self.position_type != 1:
                    print(f"Detected rigid float3 position layout for {self.name}: "
                          f"stride=16, weight_count=1, binding_count=1, normals=float.")
                self.position_type = 1
                position_length = 12

            # guessing weight type
            index_size = {'uint8':1,'uint16':2}
            weight_length = self.vertex_stride - position_length - (self.weight_count * index_size[self.vertex_weight_index_type])
            print("Weight length : ", weight_length, self.weight_count, (weight_length / self.weight_count if self.weight_count else 0))
            if self.weight_count == 0:
                print("WARNING: Weight count is 0; keeping default uint8_norm weight type.")
            elif self.is_rigid_single_binding_float3_layout():
                # Rigid single-binding float3 meshes do not use meaningful per-vertex
                # skin weights. Keep a harmless default and suppress the ambiguous
                # 3-byte weight-layout warning for this known rigid/accessory layout.
                self.vertex_weight_type = 'uint8_norm'
            elif weight_length / self.weight_count == 2:
                self.vertex_weight_type = 'uint16_norm'
            elif weight_length / self.weight_count == 3:
                print("WARNING: unusual 3-byte-per-weight-slot layout guessed as uint16_norm; packed uint8 physical layout will also be tested.")
                self.vertex_weight_type = 'uint16_norm'
            else:
                self.vertex_weight_type = 'uint8_norm'



            storage_layout = self.get_vertex_weight_storage_layout()
            print(f'\nName = {self.name}'
                  f'\nVertex Stride: {self.vertex_stride}'
                  f'\nNormals Stride: {self.normals_stride}'
                  f'\nNormals Type: {self.normal_type}'
                  f'\nPossible Normal Length: {possible_normal_length}'
                  f'\nUV Count: {self.uv_count}'
                  f'\nColor Count: {self.color_count}'
                  f'\nWeight Count: {self.weight_count}'
                  f'\nPhysical Weight Storage Count: {storage_layout["count"]}'
                  f'\nWeight Type: {self.vertex_weight_type}'
                  f'\nPhysical Weight Storage Type: {storage_layout["weight_type"]}'
                  f'\nIndex Type: {self.vertex_weight_index_type}')
            print("-" * 72)
            print(f"LOAD MESH END: {self.name}")
            print("-" * 72)
        def write(self, f):
            f.seek(self.lod_count_offset)
            lod_count = br.uint8(f)
            f.seek(4, 1)
            for l in range(self.lod_count):
                self.lods[l].write(f)
        def write_remap_bindings(self, f, index_remap):
            f.seek(self.binding_count_offset + 2) #+2 to skip count
            for i in range(self.binding_count):
                f.seek(64,1)
                old_index = br.uint16(f)
                f.seek(-2,1)
                f.write(bp.uint16(index_remap[old_index]))

        def extract_mesh_file(self,f):
            """
            Creates a file gathering the raw data of all Lods the Mesh.
            :param f: combined mmb file that contains the header and data.
            :return: Path to the extracted raw_mesh file.
            """
            extract_file = io.BytesIO()
            for lod in reversed(self.lods):
                # print(f'Copy at {lod.data_offset} size {lod.data_size}')
                CopyFile(f, extract_file, lod.data_offset, lod.data_size)
            # print(f'Total size: {sum(lod.data_size for lod in self.lods)}')
            return extract_file

    class Bone:
        def __init__(self,f):
            self.name = br.name(f)
            self.matrix = br.matrix_4x4(f)
            self.parent_index = br.uint16(f)
            self.mesh_matrix = None
        def set_mesh_matrix(self,matrix):
            if self.mesh_matrix is None:
                self.mesh_matrix = matrix

    def __init__(self):
        super().__init__()
        self.name = ""
        self.bone_count = 0
        self.bones = []
        self.mesh_count_offset = 0
        self.mesh_count = 0
        self.meshes = []
        self.end_bytes = None # bytes at the end of the meshes sections
    def parse(self,f):
        super().parse(f)
        print("Bone Count Offset:", f.tell())
        self.bone_count = br.uint32(f)
        for b in range(self.bone_count):
            self.bones.append(self.Bone(f))
        print("Mesh Count Offset:", f.tell())
        self.mesh_count_offset = f.tell()
        self.mesh_count = br.uint32(f)
        for m in range(self.mesh_count):
            mesh = self.Mesh(self,index = m)
            mesh.parse(f)
            self.meshes.append(mesh)
        length =  br.uint32(f)
        f.seek(-4,1)
        self.end_bytes = f.read(length)

        # for i,b in enumerate(self.bones):
        #     print(i, b.name)
        #     print(b.mesh_matrix)
        #     print("_")
        #     print(b.matrix)
        #     print("____________________")
        #     if b.mesh_matrix is None:
        #         print("*/*/*/*/*/*/*/*/*/*")

    def write(self, f):
        super().write(f)
        f.seek(12)
        bone_count = br.uint32(f)
        for b in range(bone_count):
            self.Bone(f)
        mesh_count = br.uint32(f)
        for m in range(mesh_count):
            self.meshes[m].write(f)
    def clear(self):
        self.bones = []
        self.meshes = []
        self.end_bytes = None
    def get_sorted_lods(self):
        lod_map = {}
        for m in self.meshes:
            for l in m.lods:
                lod_map[l] = l.data_offset
        sorted_lods = {k: v for k, v in sorted(lod_map.items(), key=lambda item: item[1])}
        return sorted_lods
    def get_mesh_data_start_offset(self):
        lods = self.get_sorted_lods()
        first_lod = next(iter(lods))
        print("Mesh Data Start Offset = ",first_lod.data_offset)
        return first_lod.data_offset

