"""Read FAT12/16 superfloppy images, including trimmed deployment images."""
import struct
from pathlib import Path


class FatImage:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        if len(self.data) < 512 or self.data[510:512] != b'\x55\xaa':
            raise ValueError('Not a FAT filesystem image (firmware binaries are unsupported)')
        (self.sector, self.spc, reserved, fats, entries, total,
         _, fat_sectors) = struct.unpack_from('<HBHBHHBH', self.data, 11)
        if self.sector not in (512, 1024, 2048, 4096) or not self.spc or not fat_sectors:
            raise ValueError('Unsupported FAT geometry')
        total = total or struct.unpack_from('<I', self.data, 32)[0]
        root_sectors = (entries * 32 + self.sector - 1) // self.sector
        self.fat = self.read(reserved * self.sector, fat_sectors * self.sector)
        self.root_offset = (reserved + fats * fat_sectors) * self.sector
        self.root_size = entries * 32
        self.data_offset = self.root_offset + root_sectors * self.sector
        self.cluster_size = self.sector * self.spc
        self.clusters = (total - self.data_offset // self.sector) // self.spc
        self.bits = 12 if self.clusters < 4085 else 16
        if self.clusters >= 65525:
            raise ValueError('FAT32 is not supported')

    def read(self, offset, size):
        if offset < 0 or offset + size > len(self.data):
            raise ValueError('Image is truncated before allocated file data; use the full t4s3-vfs.img')
        return self.data[offset:offset + size]

    def chain(self, cluster):
        seen = set()
        while cluster < (0xff8 if self.bits == 12 else 0xfff8):
            if cluster < 2 or cluster >= self.clusters + 2 or cluster in seen:
                raise ValueError('Invalid or cyclic FAT cluster chain')
            seen.add(cluster)
            yield self.read(self.data_offset + (cluster - 2) * self.cluster_size,
                            self.cluster_size)
            offset = cluster * 3 // 2 if self.bits == 12 else cluster * 2
            if offset + 2 > len(self.fat):
                raise ValueError('Invalid FAT index')
            value = int.from_bytes(self.fat[offset:offset + 2], 'little')
            cluster = ((value >> 4 if cluster & 1 else value & 0xfff)
                       if self.bits == 12 else value)

    def files(self):
        result = {}
        visited = set()

        def walk(raw, prefix=''):
            long_name = {}
            for offset in range(0, len(raw), 32):
                entry = raw[offset:offset + 32]
                if not entry or entry[0] == 0:
                    break
                if entry[0] == 0xe5:
                    long_name.clear()
                    continue
                if entry[11] == 15:
                    if entry[0] & 0x40:
                        long_name.clear()
                    part = entry[1:11] + entry[14:26] + entry[28:32]
                    long_name[entry[0] & 31] = part.decode('utf-16le').split('\x00')[0].rstrip('\uffff')
                    continue
                short = entry[:8].decode('cp437').rstrip()
                ext = entry[8:11].decode('cp437').rstrip()
                name = ''.join(long_name[k] for k in sorted(long_name)) if long_name else (short + ('.' + ext if ext else '')).lower()
                long_name.clear()
                if name in ('.', '..') or entry[11] & 8:
                    continue
                if not name or any(c in name for c in '/\\:'):
                    raise ValueError('Unsafe filename in image')
                cluster = struct.unpack_from('<H', entry, 26)[0]
                size = struct.unpack_from('<I', entry, 28)[0]
                path = prefix + name
                if entry[11] & 16:
                    if cluster in visited:
                        raise ValueError('Cyclic FAT directory')
                    visited.add(cluster)
                    walk(b''.join(self.chain(cluster)), path + '/')
                else:
                    content = b''.join(self.chain(cluster)) if size else b''
                    if len(content) < size:
                        raise ValueError('File cluster chain is too short')
                    result[path] = content[:size]
        walk(self.read(self.root_offset, self.root_size))
        return result

    def extract(self, destination):
        for name, content in self.files().items():
            target = Path(destination) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
