class cpuMEM:
    nes = None
    def __init__(self, nes):
        self.nes = nes
        
    def read_byte(self, address):
        if address < 0x2000:
            return self.nes.ram[address % 0x0800]
        elif address < 0x4000:
            return self.nes.ppu.readRegister(0x2000 + address % 8)
        elif address == 0x4014:
            return self.nes.ppu.readRegister(address)
        elif address == 0x4015:
            # APU
            # return self.nes.APU.readRegister(address)
            return 0
        elif address == 0x4016:
            # read the controller 1
            return 0
        elif address == 0x4017:
            # read controller 2
            return 0
        elif address >= 0x6000:
            return self.nes.mmap.read(address)
        else:
            print("bad cpu read at " + str(address))
            input()
        return 0

    def write_byte(self, address, value):
        if address < 0x2000:
            self.nes.ram[address % 0x0800] = value
        elif address < 0x4000:
            self.nes.ppu.writeRegister(0x2000 + (address % 8), value)
        elif address < 0x4014:
            # apu register
            return
        elif address == 0x4014:
            self.nes.ppu.writeRegister(address, value)
        elif address == 0x4015:
            # apu thing
            print("please implement the apu")
        elif address == 0x4016:
            # write controller
            print("controllers come hither")
        elif address == 0x4017:
            # apu write register
            print("apu write register")
        elif address < 0x6000:
            # io registers
            print("io registers")
        elif address >= 0x6000:
            self.nes.mmap.write(address, value)
        else:
            print("invalid cpu write to memory")

class ppuMEM:
    nes = None
    mode = 0
    
    def __init__(self, nes):
        self.nes = nes

    def read_byte(self, address):
        address = address % 0x4000
        if address < 0x2000:
            return self.nes.mmap.read(address)
        elif address < 0x3F00:
            # mirror
            mode = self.nes.rom.mirroring
            return(self.nes.ppu.nameTableData[mirror_address(mode, address) % 2048])
        elif address < 0x4000:
            return self.nes.ppu.readPalette(address % 32)
        else:
            print("invalid read at " + str(address))
        return 0

    def write_byte(self, address, value):
        address = address % 0x4000
        if address < 0x2000:
            self.nes.mmap.write(address, value)
        elif address < 0x3f00:
            mode = self.nes.rom.mirroring
            self.nes.ppu.nameTableData[mirror_address(mode, address) % 2048] = value
        elif address < 0x4000:
            self.nes.ppu.writePalette(address % 32, value)
        else:
            print("invalid ppu memory write at " + str(address))

mirror_lookup = [[0, 0, 1, 1], [0, 1, 0, 1], [0, 0, 0, 0], [1, 1, 1, 1], [0, 1, 2, 3]]

def mirror_address(mode, address):
    address = (address - 0x2000) % 0x1000
    table = address // 0x0400
    offset = address % 0x0400
    return 0x2000 + mirror_lookup[int(mode)][table] * 0x0400 + offset
