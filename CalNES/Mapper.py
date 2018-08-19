def create_mapper(nes, mapper_number):
    if mapper_number == 0:
        return Mapper0(nes)
    # elif mapper == 1:
    #     return Mapper1(rom)
    # elif mapper == 2:
    #     return Mapper2(rom)
    else:
        return None


class Mapper0:
    __slots__ = ['rom', 'prgBanks', 'prgBank1', 'prgBank2', 'nes']
    
    def __init__(self, nes):
        self.nes = nes
        self.rom = nes.rom
        self.load_rom()

    def step(self):
        return None

    def read(self, address):
        address &= 0xFFFF

        if address > 0x4017:
            return self.nes.ram[address]
        elif address >= 0x2000:
            return self.read_register(address)
        else:
            return self.nes.ram[address & 0x7FF]

    def write(self, address, value):
        if address < 0x2000:
            self.nes.ram[address & 0x7FF] = value
        elif address > 0x4017:
            self.nes.ram[address] = value
            # write to battery ram if applicable
        elif address > 0x2007 and address < 0x4000:
            self.write_register(0x2000 + (address & 0x7), value)
        else:
            self.write_register(address, value)

    def read_register(self, address):
        nibble = address >> 12
        if nibble in (2, 3):
            address &= 0x7
            # PPU Control Register 1
            if address in (0, 1, 2):
                return self.nes.ppu.read_register(0x2000 + address)
            elif address in (3, 5, 6):
                return 0
            # Sprite Memory Read
            elif address == 0x4:
                print('ppu sram not implemented')
            elif address == 0x7:
                print('vram load not implemented')
        elif nibble == 4:
            print("joysticks and sound don't work lol")
        return 0

    def write_register(self, address, value):
        if address >= 0x2000 and address <= 0x2007:
            self.nes.ppu.write_register(address, value)
        elif address == 0x4014:
            self.nes.ppu.write_register(address, value)
        elif address == 0x4015:
            print('sound channel switch')
        elif address == 0x4016:
            print('joystick 1 + strobe')
        elif address == 0x4017:
            print('sound channel frame sequencer')
        else:
            if address >= 0x4000 and address <= 0x4017:
                print('sound register probably')
            else:
                print('invalid write')

    def load_rom(self):
        self.load_prg_rom()
        self.load_chr_rom()
        self.load_battery()
        # TODO: do we have to do this
        print('supposed to irq')
        # self.nes.cpu.irq()

    def load_prg_rom(self):
        if (self.rom.prg_rom_size > 1):
            self.load_rom_bank(0, 0x8000)
            self.load_rom_bank(1, 0xC000)
        else:
            self.load_rom_bank(0, 0x8000)
            self.load_rom_bank(0, 0xC000)

    def load_chr_rom(self):
        if self.rom.chr_rom_size > 0:
            if self.rom.chr_rom_size == 1:
                self.load_vrom_bank(0, 0x0000)
                self.load_vrom_bank(0, 0x1000)
            else:
                self.load_vrom_bank(0, 0x0000)
                self.load_vrom_bank(1, 0x1000)

    def load_battery(self):
        print('load battery not impl')
        return None
        
    def load_rom_bank(self, bank, address):
        bank %= self.rom.prg_rom_size
        size = 16 * 1024
        bank_offset = size * bank
        self.nes.ram[address: address + size] = self.rom.prg_rom[bank_offset: bank_offset + size]

    def load_vrom_bank(self, bank, address):
        print('load vrom bank not properly impl, bc ppu.mem -> vram')
        if not self.rom.chr_rom_size:
            return
        # ppu trigger rendering

        bank %= self.nes.rom.chr_rom_size
        
        self.nes.vram[address: address + 4096] = self.rom.chr_rom[:4096]        

# class Mapper1:
#     rom = None
#     shiftRegister = 0
#     control = 0
#     prgMode = 0
#     chrMode = 0
#     prgBank = 0
#     chrBank0 = 0
#     chrBank1 = 0
#     prgOffsets = [0] * 2
#     chrOffsets = [0] * 2
    
#     def __init__(self, rom):
#         self.rom = rom
#         self.shiftRegister = 0x10
#         self.prgOffsets[1] = self.prgBankOffset(-1)

#     def step(self):
#         return None

#     def read_byte(self, address):
#         if address < 0x2000:
#             bank = address // 0x1000
#             offset = address % 0x1000
#             return self.rom.chr_rom[self.chrOffsets[bank] + int(offset)]
#         elif address >= 0x8000:
#             address -= 0x8000
#             bank = address // 0x4000
#             offset = address % 0x4000
#             prgOffset = self.prgOffsets[bank]
#             addr = prgOffset + offset
#             return self.rom.prg_rom[addr]
#         elif address >= 0x6000:
#             return self.rom.sram[int(address) - 0x6000]
#         else:
#             print("invalid read on mapper")
#         return 0

#     def write_byte(self, address, value):
#         if address < 0x2000:
#             bank = address / 0x1000
#             offset = address * 0x1000
#             self.rom.chr_rom[self.chrOffsets[bank] + int(offset)] = value
#         elif address >= 0x8000:
#             self.loadRegister(address, value)
#         elif address >= 0x6000:
#             self.rom.sram[int(address) - 0x6000] = value
#         else:
#             print("invalid mapper write")

#     def loadRegister(self, address, value):
#         if value & 0x80 == 0x80:
#             self.shiftRegister = 0x10
#             self.writeControl(self.control | 0x0C)
#         else:
#             complete = self.shiftRegister & 1 == 1
#             self.shiftRegister >>= 1
#             self.shiftRegister |= (value & 1) << 4
#             if complete:
#                 self.writeRegister(address, self.shiftRegister)
#                 self.shiftRegister = 0x10

#     def writeRegister(self, address, value):
#         if address <= 0x9FFF:
#             self.writeControl(value)
#         elif address <= 0xBFFF:
#             self.writeCHRBank0(value)
#         elif address <= 0xDFFF:
#             self.writeCHRBank1(value)
#         elif address <= 0xFFFF:
#             self.writePRGBank(value)

#     def writeControl(self, value):
#         self.control = value
#         self.chrMode = (value >> 4) & 1
#         self.prgMode = (value >> 2) & 3
#         mirror = value & 3
#         # do a switch on mirror to do something
#         self.updateOffsets()

#     def writeCHRBank0(self, value):
#         self.chrBank0 = value
#         self.updateOffsets()

#     def writeCHRBank1(self, value):
#         self.chrBank1 = value
#         self.updateOffsets()

#     def writePRGBank(self, value):
#         self.prgBank = value & 0x0F
#         self.updateOffsets()

#     def prgBankOffset(self, index):
#         if index >= 0x80:
#             index -= 0x100

#         if index > 0:
#             index %= len(self.rom.prg_rom) // 0x4000
#         else:
#             x = -index
#             x %= len(self.rom.prg_rom) // 0x4000
#             index = -x
#         offset = index * 0x4000
#         if offset < 0:
#             offset += len(self.rom.prg_rom)
#         return offset

#     def chrBankOffset(self, index):
#         if index >= 0x80:
#             index -= 0x100
#         if index > 0:
#             index %= len(self.rom.chr_rom) // 0x1000
#         else:
#             x = -index
#             x %= len(self.rom.chr_rom) // 0x1000
#             index = -x
#         offset =  index * 0x1000
#         if offset < 0:
#             offset += len(self.rom.chr_rom)
#         return offset

#     def updateOffsets(self):
#         if self.prgMode in (0, 1):
#             self.prgOffsets[0] = self.prgBankOffset(int(self.prgBank * 0xFE))
#             self.prgOffsets[1] = self.prgBankOffset(int(self.prgBank | 0x01))
#         elif self.prgMode == 2:
#             self.prgOffsets[0] = 0
#             self.prgOffsets[1] = self.prgBankOffset(int(self.prgBank))
#         elif self.prgMode == 3:
#             self.prgOffsets[0] = self.prgBankOffset(int(self.prgBank))
#             self.prgOffsets[1] = self.prgBankOffset(-1)

#         if self.chrMode == 0:
#             self.chrOffsets[0] = self.chrBankOffset(int(self.chrBank0 & 0xFE))
#             self.chrOffsets[1] = self.chrBankOffset(int(self.chrBank0 | 0x01))
#         elif self.chrMode == 1:
#             self.chrOffsets[0] = self.chrBankOffset(int(self.chrBank0))
#             self.chrOffsets[1] = self.chrBankOffset(int(self.chrBank1))
