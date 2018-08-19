"""
This is pretty much fogleman/nes's PPU
I'm working on understanding it + re-implementing it
"""
from .Screen import Screen
import random
import pygame


class PPU:
    __slots__ = ['nes', 'mem', 'cycle', 'scanline', 'frame',
                 'paletteData', 'nameTableData', 'oamData', 'front',
                 'back', 'v', 't', 'x', 'w', 'f', 'register',
                 'nmiOccurred', 'nmiOutput', 'nmiPrevious', 'nmiDelay',
                 'nameTableByte', 'attributeTableByte', 'lowTileByte',
                 'highTileByte', 'tileData', 'spriteCount', 'spritePatterns',
                 'spritePositions', 'spritePriorities', 'spriteIndexes', 'flagNameTable',
                 'flagIncrement', 'flagSpriteTable', 'flagBackgroundTable',
                 'flagSpriteSize', 'flagMasterSlave', 'flagGrayscale',
                 'flagShowLeftBackground', 'flagShowLeftSprites', 'flagShowSprites',
                 'flagRedTint', 'flagShowBackground', 'flagGreenTint',
                 'flagBlueTint', 'flagSpriteZeroHit',
                 'flagSpriteOverflow', 'oamAddress', 'bufferedData']


    def __init__(self, nes, mem):
        self.cycle = 0 # 0-340
        self.scanline = 0 # 0-261, 0-239=visible, 240=post, 241-260=vblank, 261=pre
        self.frame = 0 # frame counter

        self.paletteData = [0] * 32
        self.nameTableData = [0] * 2048
        self.oamData = [0] * 256

        # PPU Registers
        self.v = 0 # current vram address, 15b
        self.t = 0 # temp vram address, 15b
        self.x = 0 # fine x scroll 3b
        self.w = 0 # write toggle 1b
        self.f = 0 # even/odd frame flag 1b

        self.register = 0 # byte? not sure what this is for

        # nmi flags, what is this lol
        self.nmiOccurred = False
        self.nmiOutput = False
        self.nmiPrevious = False
        self.nmiDelay = 0 # 8b

        self.nameTableByte = 0 #      byte
        self.attributeTableByte = 0 #  byte
        self.lowTileByte = 0 #        byte
        self.highTileByte = 0 #      byte
        self.tileData = 0 #           uint64

        # sprite temporary variables
        self.spriteCount = 0 #      int
        self.spritePatterns = [0] * 8 #   [8]uint32
        self.spritePositions = [0] * 8 # [8]byte
        self.spritePriorities = [0] * 8# [8]byte
        self.spriteIndexes = [0] * 8 #    [8]byte

        # $2000 PPUCTRL
        self.flagNameTable = 0 #       byte // 0: $2000; 1: $2400; 2: $2800; 3: $2C00
        self.flagIncrement = 0 #      byte // 0: add 1; 1: add 32
        self.flagSpriteTable = 0 #     byte // 0: $0000; 1: $1000; ignored in 8x16 mode
        self.flagBackgroundTable = 0 # byte // 0: $0000; 1: $1000
        self.flagSpriteSize = 0 #      byte // 0: 8x8; 1: 8x16
        self.flagMasterSlave = 0 #    byte // 0: read EXT; 1: write EXT

        # $2001 PPUMASK
        self.flagGrayscale = 0 #          byte // 0: color; 1: grayscale
        self.flagShowLeftBackground = 0# byte // 0: hide; 1: show
        self.flagShowLeftSprites = 0 #    byte // 0: hide; 1: show
        self.flagShowBackground = 0 #    byte // 0: hide; 1: show
        self.flagShowSprites = 0 #       byte // 0: hide; 1: show
        self.flagRedTint = 0 #            byte // 0: normal; 1: emphasized
        self.flagGreenTint = 0 #         byte // 0: normal; 1: emphasized
        self.flagBlueTint = 0 #          byte // 0: normal; 1: emphasized

        # $2002 PPUSTATUS
        self.flagSpriteZeroHit = 0 #   byte
        self.flagSpriteOverflow = 0 # byte

        # $2003 OAMADDR
        self.oamAddress = 0 # byte

        # $2007 PPUDATA
        self.bufferedData = 0 # byte // for buffered reads

        self.nes = nes
        self.mem = mem
        self.back = Screen()
        self.front = Screen()
        self.reset()

    def reset(self):
        self.cycle = 340
        self.scanline = 240
        self.frame = 0
        self.writeControl(0)
        self.writeMask(0)
        self.writeOAMAddress(0)

    def readPalette(self, address):
        if address >= 16 and address % 4 == 0:
            address -= 16
        return self.paletteData[address % 32]

    def writePalette(self, address, value):
        if address >= 16 and address % 4 == 0:
            address -= 16
        self.paletteData[address] = value

    def read_register(self, address):
        if address == 0x2002:
            return self.readStatus()
        if address == 0x2004:
            return self.readOAMData()
        if address == 0x2007:
            return self.readData()
        return 0

    # consider rewriting this with hashing
    def write_register(self, address, value):
        value = value & 0xFF
        self.register = value
        if address == 0x2000:
            self.writeControl(value)
        if address == 0x2001:
            self.writeMask(value)
        if address == 0x2003:
            self.writeOAMAddress(value)
        if address == 0x2004:
            self.writeOAMData(value)
        if address == 0x2005:
            self.writeScroll(value)
        if address == 0x2006:
            self.writeAddress(value)
        if address == 0x2007:
            self.writeData(value)
        if address == 0x4014:
            self.writeDMA(value)

    def writeControl(self, ctrl):
        self.flagNameTable = ctrl & 3
        self.flagIncrement = (ctrl >> 2) & 1
        self.flagSpriteTable = (ctrl >> 3) & 1
        # self.flagSpriteTable = 0
        self.flagBackgroundTable = (ctrl >> 4) & 1
        self.flagSpriteSize = (ctrl >> 5) & 1
        self.flagMasterSlave = (ctrl >> 6) & 1
        self.nmiOutput = ((ctrl >> 7) & 1) == 1
        self.nmiChange()
        self.t = (self.t & 0xF3FF) | ((ctrl & 0x03) << 10)

    def writeMask(self, mask):
        self.flagGrayscale = mask & 1
        self.flagShowLeftBackground = (mask >> 1) & 1
        self.flagShowLeftSprites = (mask >> 2) & 1
        self.flagShowBackground = (mask >> 3) & 1
        self.flagShowSprites = (mask >> 4) & 1
        self.flagRedTint = (mask >> 5) & 1
        self.flagGreenTint = (mask >> 6) & 1
        self.flagBlueTint = (mask >> 7) & 1

    def readStatus(self):
        result = self.register & 0x1F
        result |= self.flagSpriteOverflow << 5
        result |= self.flagSpriteZeroHit << 6
        if self.nmiOccurred:
            result |= 1 << 7
        self.nmiOccurred = False
        self.nmiChange()
        self.w = 0
        return result & 0xFF

    def writeOAMAddress(self, oam):
        self.oamAddress = oam

    def readOAMData(self):
        return self.oamData[self.oamAddress]

    def writeOAMData(self, value):
        self.oamData[self.oamAddress] = value
        self.oamAddress = (self.oamAddress + 1) & 0xFF

    def writeScroll(self, value):
        if self.w == 0:
            self.t = (self.t & 0xFFE0) | (value >> 3)
            self.x = value & 0x07
            self.w = 1
        else:
            self.t = (self.t & 0x8FFF) | ((value & 0x07) << 12)
            self.t = (self.t & 0xFC1F) | ((value & 0xF8) << 2)
            self.w = 0

    def writeAddress(self, value):
        if self.w == 0:
            self.t = (self.t & 0x80FF) | ((value & 0x3F) << 8)
            self.w = 1
        else:
            self.t = (self.t & 0xFF00) | value
            self.v = self.t
            self.w = 0

    def readData(self):
        value = self.mem.read_byte(self.v)
        if self.v % 0x4000 < 0x3F00:
            buffered = self.bufferedData
            self.bufferedData = value
            value = buffered
        else:
            self.bufferedData = self.mem.read_byte(self.v - 0x1000)
        # increment address
        if self.flagIncrement == 0:
            self.v += 1
        else:
            self.v += 32
        return value

    def writeData(self, value):
        self.mem.write_byte(self.v, value)
        if self.flagIncrement == 0:
            self.v += 1
        else:
            self.v += 32

    def writeDMA(self, value):
        cpu = self.nes.cpu
        address = (value << 8) & 0xFFFF
        for i in range(256):
            self.oamData[self.oamAddress] = self.nes.ram.read_byte(address)
            # self.oamAddress = (self.oamAddress + 1) & 0xFF
            self.oamAddress += 1
            address += 1
        cpu.stall += 513
        if cpu.cycles % 2 == 1:
            cpu.stall += 1

    def incrementX(self):
        if self.v & 0x001F == 31:
            self.v &= 0xFFE0
            self.v ^= 0x0400
        else:
            self.v += 1

    def incrementY(self):
        if self.v & 0x7000 != 0x7000:
            self.v += 0x1000
        else:
            self.v &= 0x8FFF
            y = (self.v & 0x03E0) >> 5
            if y == 29:
                y = 0
                self.v ^= 0x0800
            elif y == 31:
                y = 0
            else:
                y += 1
            self.v = (self.v & 0xFC1F) | (y << 5)

    def copyX(self):
        self.v = (self.v & 0xFBE0) | (self.t & 0x041F)

    def copyY(self):
        self.v = (self.v & 0x841F) | (self.t & 0x7BE0)

    def nmiChange(self):
        nmi = self.nmiOutput and self.nmiOccurred
        if nmi and not self.nmiPrevious:
            self.nmiDelay = 15
        self.nmiPrevious = nmi

    def setVerticalBlank(self):
        self.front, self.back = self.back, self.front
        self.nmiOccurred = True
        self.nmiChange()

    def clearVerticalBlank(self):
        self.nmiOccurred = False
        self.nmiChange()

    # this output is higher for some reason
    def fetchNameTableByte(self):
        address = 0x2000 | (self.v & 0x0FFF)
        self.nameTableByte = self.mem.read_byte(address)

    def fetchAttributeTableByte(self):
        address = 0x23C0 | (self.v & 0x0C00) | ((self.v >> 4) & 0x38) | ((self.v >> 2) & 0x07)
        shift = ((self.v >> 4) & 4) | (self.v & 2)
        self.attributeTableByte = (((self.mem.read_byte(address) >> shift) & 3) << 2)

    def fetchLowTileByte(self):
        fineY = (self.v >> 12) & 7
        table = self.flagBackgroundTable
        tile = self.nameTableByte
        address = 0x1000 * table + tile * 16 + fineY
        self.lowTileByte = self.mem.read_byte(address)

    def fetchHighTileByte(self):
        fineY = (self.v >> 12) & 7
        table = self.flagBackgroundTable
        tile = self.nameTableByte
        address = 0x1000 * table + tile * 16 + fineY
        self.highTileByte = self.mem.read_byte(address + 8)

    def storeTileData(self):
        data = 0
        for i in range(8):
            a = self.attributeTableByte
            p1 = (self.lowTileByte & 0x80) >> 7
            p2 = (self.highTileByte & 0x80) >> 6
            self.lowTileByte <<= 1
            self.highTileByte <<= 1
            data <<= 4
            data |= (a | p1 | p2)
        self.tileData |= data

    def fetchTileData(self):
        return self.tileData >> 32

    def backgroundPixel(self):
        if self.flagShowBackground == 0:
            return 0
        # TODO: wtf
        data = self.fetchTileData()
        data >>= ((7 - self.x) * 4)
        return data & 0x0F

    def spritePixel(self):
        if self.flagShowSprites == 0:
            return (0, 0)
        for i in range(self.spriteCount):
            offset = (self.cycle - 1) - int(self.spritePositions[i])
            if offset < 0 or offset > 7:
                continue
            offset = 7 - offset
            color = (self.spritePatterns[i] >> (offset * 4)) & 0x0F
            if color % 4 == 0:
                continue
            return (i, color)
        return (0, 0)

    def renderPixel(self):
        x = self.cycle - 1
        y = self.scanline
        background = self.backgroundPixel()
        i, sprite = self.spritePixel()
        if x < 8 and self.flagShowLeftBackground == 0:
            background = 0
        if x < 8 and self.flagShowLeftSprites == 0:
            sprite = 0
        b = (background % 4) != 0
        s = (sprite % 4) != 0
        color = 0
        if not b and not s:
            color = 0
        elif not b and s:
            color = sprite | 0x10
        elif b and not s:
            color = background
        else:
            if self.spriteIndexes[i] == 0 and x < 255:
                self.flagSpriteZeroHit = 1
            if self.spritePriorities[i] == 0:
                color = sprite | 0x10
            else:
                color = background
        c = Palette[self.readPalette(color) % 64]
        self.back.SetRGBA(x, y, c)

    def fetchSpritePattern(self, i, row):
        tile = self.oamData[(i * 4) + 1]
        attributes = self.oamData[(i * 4) + 2]
        address = 0
        if self.flagSpriteSize == 0:
            if attributes & 0x80 == 0x80:
                row = 7 - row
            table = self.flagSpriteTable
            address = 0x1000 * table + tile * 16 + row
        else:
            if attributes & 0x80 == 0x80:
                row = 15 - row
            table = tile & 1
            tile &= 0xFE
            if row > 7:
                tile += 1
                row -= 8
            address = 0x1000 * table + tile * 16 + row
        address &= 0xFFFF
        a = (attributes & 3) << 2
        lowTileByte = self.mem.read_byte(address)
        highTileByte = self.mem.read_byte(address + 8)
        data = 0
        for i in range(8):
            p1, p2 = 0, 0
            if attributes & 0x40 == 0x40:
                p1 = (lowTileByte & 1) 
                p2 = (highTileByte & 1) << 1
                lowTileByte >>= 1
                highTileByte >>= 1
            else:
                p1 = (lowTileByte & 0x80) >> 7
                p2 = (highTileByte & 0x80) >> 6
                lowTileByte <<= 1
                highTileByte <<= 1
            data <<= 4
            data |= (a | p1 | p2)
        return data

    def evaluateSprites(self):
        h = 0
        if self.flagSpriteSize == 0:
            h = 8
        else:
            h = 16
        count = 0
        for i in range(64):
            y = self.oamData[i * 4]
            a = self.oamData[i * 4 + 2]
            x = self.oamData[i * 4 + 3]
            row = self.scanline - y
            if row < 0 or row >= h:
                continue
            if count < 8:
                self.spritePatterns[count] = self.fetchSpritePattern(i, row)
                self.spritePositions[count] = x
                self.spritePriorities[count] = (a >> 5) & 1
                self.spriteIndexes[count] = (i & 0xFF)
            count += 1
        if count > 8:
            count = 8
            self.flagSpriteOverflow = 1
        self.spriteCount = count

    def tick(self):
        if self.nmiDelay > 0:
            self.nmiDelay = (self.nmiDelay - 1) % 256
            if self.nmiDelay == 0 and self.nmiOutput and self.nmiOccurred:
                self.nes.cpu.triggerNMI()

        if self.flagShowBackground != 0 or self.flagShowSprites != 0:
            if self.f == 1 and self.scanline == 261 and self.cycle == 339:
                self.cycle = 0
                self.scanline = 0
                self.frame += 1
                self.f ^= 1
                return
        self.cycle += 1
        if self.cycle > 340:
            self.cycle = 0
            self.scanline += 1
            if self.scanline > 261:
                self.scanline = 0
                self.frame += 1
                self.f ^= 1

    def step(self):
        self.tick()
        renderingEnabled = self.flagShowBackground != 0 or self.flagShowSprites != 0
        preline = self.scanline == 261
        visibleline = self.scanline < 240
        renderline = preline or visibleline
        prefetchcycle = self.cycle >= 321 and self.cycle <= 336
        visiblecycle = self.cycle >= 1 and self.cycle <= 256
        fetchcycle = prefetchcycle or visiblecycle

        if renderingEnabled:
            if visibleline and visiblecycle:
                self.renderPixel()
            if renderline and fetchcycle:
                self.tileData <<= 4
                x = self.cycle % 8
                if x == 1:
                    self.fetchNameTableByte()
                if x == 3:
                    self.fetchAttributeTableByte()
                if x == 5:
                    self.fetchLowTileByte()
                if x == 7:
                    self.fetchHighTileByte()
                if x == 0:
                    self.storeTileData()
            if preline and self.cycle >= 280 and self.cycle <= 304:
                self.copyY()
            if renderline:
                if fetchcycle and self.cycle % 8 == 0:
                    self.incrementX()
                if self.cycle == 256:
                    self.incrementY()
                if self.cycle == 257:
                    self.copyX()
        if renderingEnabled:
            if self.cycle == 257:
                if visibleline:
                    self.evaluateSprites()
                else:
                    self.spriteCount = 0

        if self.scanline == 241 and self.cycle == 1:
            self.setVerticalBlank()
        if preline and self.cycle == 1:
            self.clearVerticalBlank()
            self.flagSpriteZeroHit = 0
            self.flagSpriteOverflow = 0

Palette = [0] * 64
colors = [0x666666, 0x002A88, 0x1412A7, 0x3B00A4, 0x5C007E, 0x6E0040, 0x6C0600, 0x561D00,
	  0x333500, 0x0B4800, 0x005200, 0x004F08, 0x00404D, 0x000000, 0x000000, 0x000000,
	  0xADADAD, 0x155FD9, 0x4240FF, 0x7527FE, 0xA01ACC, 0xB71E7B, 0xB53120, 0x994E00,
	  0x6B6D00, 0x388700, 0x0C9300, 0x008F32, 0x007C8D, 0x000000, 0x000000, 0x000000,
	  0xFFFEFF, 0x64B0FF, 0x9290FF, 0xC676FF, 0xF36AFF, 0xFE6ECC, 0xFE8170, 0xEA9E22,
	  0xBCBE00, 0x88D800, 0x5CE430, 0x45E082, 0x48CDDE, 0x4F4F4F, 0x000000, 0x000000,
	  0xFFFEFF, 0xC0DFFF, 0xD3D2FF, 0xE8C8FF, 0xFBC2FF, 0xFEC4EA, 0xFECCC5, 0xF7D8A5,
	  0xE4E594, 0xCFEF96, 0xBDF4AB, 0xB3F3CC, 0xB5EBF2, 0xB8B8B8, 0x000000, 0x000000]
for i, c in enumerate(colors):
    r = (c >> 16) & 0xFF
    g = (c >> 8) & 0xFF
    b = c & 0xFF
    Palette[i] = pygame.Color(r, g, b, 255)

