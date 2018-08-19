from enum import Enum


# Short Hex
def shex(val):
    return hex(val)[2:].upper()


def pages_differ(a, b):
    return (a & 0xFF00) != (b & 0xFF00)


# interrupts
class Interrupt(Enum):
    none = 0
    NMI = 1
    IRQ = 2


class CPU:
    __slots__ = ['done', 'mem', 'PC', 'P', 'SP', 'reg', 'opcode_to_instruction', 'stall', 'cycles', 'interrupt',
                 'page_crossed', 'debug', 'nes', 'DEBUG', 'elapsed_cycles']

    def __init__(self, nes, DEBUG):
        self.nes = nes
        self.reg = {"A": bytearray([0]),
                    "X": bytearray([0]),
                    "Y": bytearray([0])}
        self.create_opcode_table()
        self.DEBUG = DEBUG

    def reset(self):
        self.stall = 0
        self.cycles = 0
        self.elapsed_cycles = 0
        self.interrupt = Interrupt.none
        self.page_crossed = False
        self.done = False
        self.P = 0x24
        self.PC = self.read16(0xFFFC)
        # DEBUG, for nestest
        # self.PC = 0xC000
        self.SP = 0xFD
        self.A = 0
        self.X = 0
        self.Y = 0
        """$4017 = $00 (frame irq enabled)
           $4015 = $00 (all channels disabled)
           $4000-$400F = $00 (not sure about $4010-$4013)"""

    def mread(self, address):
        return self.nes.mmap.read(address)

    def read16(self, address):
        return (self.mread(address + 1) << 8) | self.mread(address)

    def mwrite(self, address, value):
        self.nes.mmap.write(address, value)

    # Executes a single instruction; replacing run_instruction for now without error handling
    def step(self):
        self.page_crossed = False
        self.elapsed_cycles += 1
        if self.stall > 0:
            self.stall -= 1
            return
        if self.cycles > 0:
            self.cycles -= 1
            return
        if self.interrupt == Interrupt.NMI:
            self.nmi()
        elif self.interrupt == Interrupt.IRQ:
            self.irq()
        self.interrupt = Interrupt.none

        old_PC = self.PC
        opcode = self.get_PC_byte()
        self.cycles += instruction_cycles[opcode]
        f = self.opcode_to_instruction[opcode]
        if self.DEBUG:
            print(self._cpu_dump(old_PC, f))
        f(opcode)
        if self.page_crossed:
            self.cycles += instruction_page_cycles[opcode]
        return

    def add_branch_cycles(self, address):
        self.cycles += 1
        if pages_differ(self.PC, address):
            self.cycles += 1

    def triggerNMI(self):
        self.interrupt = Interrupt.NMI

    def triggerIRQ(self):
        if self.I == 0:
            self.interrupt = Interrupt.IRQ

    def nmi(self):
        bytes_to_stack = bytearray([self.PC & 0xFF, self.PC >> 8])
        pointer = self.SP
        for b in bytes_to_stack:
            self.mwrite(pointer, b)
            pointer += 1
        self.PHP(0x08)
        self.PC = self.read16(0xFFFA)
        self.set_I(1)
        self.cycles += 7

    def irq(self):
        bytes_to_stack = bytearray([self.PC & 0xFF, self.PC >> 8])
        pointer = self.SP
        for b in bytes_to_stack:
            self.mwrite(pointer, b)
            pointer += 1
        self.PHP(0x08)
        self.PC = self.read16(0xFFFE)
        self.set_I(1)
        self.cycles += 7

    def get_PC_byte(self):
        byte = self.mread(self.PC)
        self.PC += 1
        return byte

    def get_zero_page_addr(self, offset=0):
        return self.get_PC_byte() + offset

    def get_zero_page_addr_x(self):
        return self.get_zero_page_addr(self.X)

    def get_zero_page_addr_y(self):
        return self.get_zero_page_addr(self.Y)

    def get_zero_page(self, offset=0):
        addr = self.get_PC_byte() + offset
        mem_byte = self.mread(addr)
        return mem_byte

    def get_zero_page_x(self):
        return self.get_zero_page(self.X)

    def get_zero_page_y(self):
        return self.get_zero_page(self.Y)

    def get_absolute_addr(self, offset=0):
        lower = self.get_PC_byte()
        upper = self.get_PC_byte()
        addr = (upper << 8 | lower) + offset
        self.page_crossed = pages_differ(self.PC, addr)
        return addr

    def get_absolute_addr_x(self):
        address = self.get_absolute_addr(self.X)
        self.page_crossed = pages_differ(address - self.X, address)
        return address

    def get_absolute_addr_y(self):
        address = self.get_absolute_addr(self.Y)
        self.page_crossed = pages_differ(address - self.Y, address)
        return address

    def get_absolute(self, offset=0):
        addr = self.get_absolute_addr(offset)
        mem_byte = self.mread(addr)
        return mem_byte

    def get_absolute_x(self):
        return self.get_absolute(self.X)

    def get_absolute_y(self):
        return self.get_absolute(self.Y)

    # This probably works
    def get_relative_addr(self):
        offset = self.convert_8bit_twos(self.get_PC_byte())
        addr = self.PC + offset
        return addr

    # TODO: Do a proof of correctness on the value returned lol
    def get_indirect_addr(self, reg_offset=0):
        # The next byte after opcode
        zero_page_addr = self.get_PC_byte()
        addr = self.mread(zero_page_addr) + (self.mread(zero_page_addr + 1) << 8)
        return addr + reg_offset

    def get_indirect_addr_x(self):
        return self.get_indirect_addr(self.X)

    def get_indirect_addr_y(self):
        address = self.get_indirect_addr(self.Y)
        self.page_crossed = pages_differ(address - (self.Y), address)
        return address

    def get_indirect(self, offset=0):
        addr = self.get_absolute_addr(offset)
        lower = self.mread(addr)
        upper = self.mread(addr + 1)
        real_addr = (upper << 8) + lower
        return self.mread(real_addr)

    def get_indirect_x(self):
        return self.get_indirect(self.X)

    def get_indirect_y(self):
        return self.get_indirect(self.Y)

    def ADC(self, opcode):
        # ***** ADC(ADd with Carry) *****
        if opcode == 0x69:  # Immediate, 2, 2
            operand = self.get_PC_byte();
        elif opcode == 0x65:  # Zero Page, 2, 3
            operand = self.get_zero_page_x()
        elif opcode == 0x75:  # Zero Page,X, 2, 4
            operand = self.get_zero_page_x()
        elif opcode == 0x6D:  # Absolute, 3, 4
            operand = self.get_absolute()
        elif opcode == 0x7D:  # Absolute,X, 3, 4
            operand = self.get_absolute_x()
        elif opcode == 0x79:  # Absolute,Y, 3, 4
            operand = self.get_absolute_y()
        elif opcode == 0x61:  # (Indirect,X) 2, 6
            operand = self.get_indirect_x()
        elif opcode == 0x71:  # (Indirect,Y) 2, 5
            operand = self.get_indirect_y()
        else:
            return self.invalid_instruction(opcode)

        result = self.A + operand + self.C
        # seeing if signed overflow
        if ((self.A ^ operand) & 0x80) == 0 and ((self.A ^ result) & 0x80) != 0:
            self.set_V(1)
        else:
            self.set_V(0)
        self.A = result & 0xFF

        self.set_C(result >> 8)
        self.set_Z(self.A == 0)
        self.set_N(self.A >> 7)

    def AHX(self, opcode):
        print('AHX not implemented')

    def ALR(self, opcode):
        print('ALR not implemented!')

    def ANC(self, opcode):
        print('ALC not implemented!')

    def AND(self, opcode):
        # ***** AND - Logical AND *****
        if opcode == 0x29:  # Immediate, 2, 2
            self.A = self.A & self.get_PC_byte()
        elif opcode == 0x25:  # Zero Page, 2, 3
            self.A = self.A & self.get_zero_page()
        elif opcode == 0x35:  # Zero Page,X, 2, 4
            self.A = self.A & self.get_zero_page_x()
        elif opcode == 0x2D:  # Absolute, 3, 4
            self.A = self.A & self.get_absolute()
        elif opcode == 0x3D:  # Absolute,X, 3, 4
            self.A = self.A & self.get_absolute_x()
        elif opcode == 0x39:  # Absolute,Y, 3, 4
            self.A = self.A & self.get_absolute_y()
        elif opcode == 0x21:  # (Indirect,X) 2, 6
            self.A = self.A & self.get_indirect_x()
        elif opcode == 0x31:  # (Indirect,Y) 2, 5
            self.A = self.A & self.get_indirect_y()
        else:
            return self.invalid_instruction(opcode)

        # update processor status
        self.set_Z(self.A == 0)
        self.set_N(self.A >> 7)

    def ARR(self, opcode):
        print('ARR not implemented!')

    def ASL(self, opcode):
        # ***** ASL - Arithmetic Shift Left: *****"""
        if opcode == 0x0A:  # Accumulator, 1, 2
            operand = self.A
            result = (self.A << 1) & 0xFF
            self.A = result

        else:
            if opcode == 0x06:  # Zero Page, 2, 5
                addr = self.get_zero_page_addr()
            elif opcode == 0x16:  # Zero Page,X, 2, 6
                addr = self.get_zero_page_addr_x()
            elif opcode == 0x0E:  # Absolute, 3, 6
                addr = self.get_absolute_addr()
            elif opcode == 0x1E:  # Absolute,X, 3, 7
                addr = self.get_absolute_addr_x()
            else:
                return self.invalid_instruction(opcode)

            operand = self.mread(addr)
            result = (operand << 1) & 0xFF
            self.set_mem(addr, result)

        self.set_C(operand >> 7)
        self.set_Z(self.A == 0)
        self.set_N(result >> 7)

    def AXS(self, opcode):
        print('AXS not implemented')

    def BCC(self, opcode):
        # ***** BCC - Branch if Carry Clear *****
        addr = self.get_relative_addr()
        if opcode == 0x90:  # Relative, 2, 2
            if not self.C:
                self.PC = addr
                self.add_branch_cycles(addr)
        else:
            return self.invalid_instruction(opcode)

    def BCS(self, opcode):
        # ***** BCS - Branch if Carry Set *****
        addr = self.get_relative_addr()
        if opcode == 0xB0:  # Relative, 2, 2
            if self.C:
                self.PC = addr
                self.add_branch_cycles(addr)
        else:
            return self.invalid_instruction(opcode)

    def BEQ(self, opcode):
        # ***** BEQ - Branch if Equal *****
        addr = self.get_relative_addr()
        if opcode == 0xF0:  # Relative, 2, 2
            if self.Z:
                self.PC = addr
                self.add_branch_cycles(addr)
        else:
            return self.invalid_instruction(opcode)

    def BIT(self, opcode):
        # ***** BIT - Bit Test *****
        if opcode == 0x24:  # Zero Page, 2, 3
            operand = self.get_zero_page()
        elif opcode == 0x2C:  # Absolute, 3, 4
            operand = self.get_absolute()
        else:
            return self.invalid_instruction(opcode)

        result = self.A & operand
        self.set_Z(result == 0)
        self.set_V(self.get_bit(operand, 6))
        self.set_N(self.get_bit(operand, 7))

    def BMI(self, opcode):
        # ***** BMI - Branch if Minus *****
        addr = self.get_relative_addr()
        if opcode == 0x30:  # Relative, 2, 2
            if self.N:
                self.PC = addr
                self.add_branch_cycles(addr)
        else:
            return self.invalid_instruction(opcode)

    def BNE(self, opcode):
        # ***** BNE - Branch if Not Equal *****
        addr = self.get_relative_addr()
        if opcode == 0xD0:  # Relative, 2, 2
            if not self.Z:
                self.PC = addr
                self.add_branch_cycles(addr)
        else:
            return self.invalid_instruction(opcode)

    def BPL(self, opcode):
        # ***** BPL - Branch if Positive *****
        addr = self.get_relative_addr()
        if opcode == 0x10:  # Relative, 2, 2
            if not self.N:
                self.PC = addr
                self.add_branch_cycles(addr)
        else:
            return self.invalid_instruction(opcode)

    def BRK(self, opcode):
        # ***** BRK - Force Interrupt *****
        if opcode == 0x00:  # Implied, 1, 7
            # Push PC and P on stack
            self.SP -= 3
            proc = self.P % 256
            bytes_to_stack = bytearray([proc, self.PC & 0xFF, self.PC >> 8])
            pointer = self.SP
            for b in bytes_to_stack:
                self.mwrite(pointer, b)
                pointer += 1
            # Set PC as IRQ vector
            lower = self.mread(0xFFFE)
            upper = self.mread(0xFFFF)
            self.PC = (upper << 8) | lower

            # Set flag
            self.set_B(1)
            self.set_I(1)
        else:
            return self.invalid_instruction(opcode)

    def BVC(self, opcode):
        # ***** BVC - Branch if OverFlow Clear *****
        addr = self.get_relative_addr()
        if opcode == 0x50:  # Relative, 2, 2
            if not self.V:
                self.PC = addr
                self.add_branch_cycles(addr)
        else:
            return self.invalid_instruction(opcode)

    def BVS(self, opcode):
        # ***** BVS - Branch if OverFlow Set *****
        addr = self.get_relative_addr()
        if opcode == 0x70:  # Relative, 2, 2
            if self.V:
                self.PC = addr
                self.add_branch_cycles(addr)
        else:
            return self.invalid_instruction(opcode)

    def CLC(self, opcode):
        # ***** CLC - Clear Carry Flag *****
        if opcode == 0x18:  # Implied, 1, 2
            self.set_C(0)
        else:
            return self.invalid_instruction(opcode)

    def CLD(self, opcode):
        # ***** CLD - Clear Decimal Mode *****
        if opcode == 0xD8:  # Implied, 1, 2
            self.set_D(0)
        else:
            return self.invalid_instruction(opcode)

    def CLI(self, opcode):
        # ***** CLI - Clear Interrupt Disable *****
        if opcode == 0x58:  # Implied, 1, 2
            self.set_I(0)
        else:
            return self.invalid_instruction(opcode)

    def CLV(self, opcode):
        # ***** CLV - Clear Overflow Flag *****
        if opcode == 0xB8:  # Implied, 1, 2
            self.set_V(0)
        else:
            return self.invalid_instruction(opcode)

    def CMD(self, opcode):
        print('CMD not implemented')

    def CMP(self, opcode):
        # ***** CMP - Compare *****
        if opcode == 0xC9:  # Immediate 2, 2
            operand = self.get_PC_byte()
        elif opcode == 0xC5:  # Zero Page 2, 3
            operand = self.get_zero_page()
        elif opcode == 0xD5:  # Zero Page,X 2, 4
            operand = self.get_zero_page_x()
        elif opcode == 0xCD:  # Absolute 3, 4
            operand = self.get_zero_page_y()
        elif opcode == 0xDD:  # Absolute,X 3, 4
            operand = self.get_absolute_x()
        elif opcode == 0xD9:  # Absolute,Y, 3, 4
            operand = self.get_absolute_y()
        elif opcode == 0xC1:  # (Indirect,X), 2, 6
            operand = self.get_indirect_x()
        elif opcode == 0xD1:  # (Indirect),Y, 2, 5
            operand = self.get_indirect_y()
        else:
            return self.invalid_instruction(opcode)

        result = (self.A - operand) & 0xFF
        self.set_C(self.A >= operand)
        self.set_Z(result == 0)
        self.set_N(result >> 7)

    def CPX(self, opcode):
        # ***** CPX - Compare X Register *****
        if opcode == 0xE0:  # Immediate 2, 2
            operand = self.get_PC_byte()
        elif opcode == 0xE4:  # Zero Page 2, 3
            operand = self.get_zero_page()
        elif opcode == 0xEC:  # Absolute, 3, 4
            operand = self.get_absolute()
        else:
            return self.invalid_instruction(opcode)

        result = (self.X - operand) & 0xFF
        self.set_C(self.X >= operand)
        self.set_Z(result == 0)
        self.set_N(result >> 7)

    def CPY(self, opcode):
        # ***** CPY - Compare Y Register *****
        if opcode == 0xC0:  # Immediate 2, 2
            operand = self.get_PC_byte()
        elif opcode == 0xC4:  # Zero Page 2, 3
            operand = self.get_zero_page()
        elif opcode == 0xCC:  # Absolute, 3, 4
            operand = self.get_absolute()
        else:
            return self.invalid_instruction(opcode)

        result = (self.Y - operand) & 0xFF
        self.set_C(self.Y >= operand)
        self.set_Z(result == 0)
        self.set_N(result >> 7)

    def DCP(self, opcode):
        print('DCP not implemented')

    def DEC(self, opcode):
        # ***** DEC - Decrement Memory *****
        if opcode == 0xC6:  # Zero Page 2, 5
            addr = self.get_zero_page_addr()
        elif opcode == 0xD6:  # Zero Page,X, 2, 6
            addr = self.get_zero_page_addr_x()
        elif opcode == 0xCE:  # Absolute, 3, 6
            addr = self.get_absolute_addr()
        elif opcode == 0xDE:  # Absolute,X, 3, 7
            addr = self.get_absolute_addr_x()
        else:
            return self.invalid_instruction(opcode)

        result = (self.mread(addr) - 1) & 0xFF
        self.mwrite(addr, result)
        self.set_Z(result == 0)
        self.set_N(result >> 7)

    def DEX(self, opcode):
        # ***** DEX - Decrement X Register *****
        if opcode == 0xCA:  # Implied 1, 2
            self.X = (self.X - 1) & 0xFF
            self.set_Z(self.X == 0)
            self.set_N(self.X >> 7)

        else:
            return self.invalid_instruction(opcode)

    def DEY(self, opcode):
        # ***** DEY - Decrement Y Register *****
        if opcode == 0x88:  # Implied 1, 2
            self.Y = (self.Y - 1) & 0xFF
            self.set_Z(self.Y == 0)
            self.set_N(self.Y >> 7)
        else:
            return self.invalid_instruction(opcode)

    def EOR(self, opcode):
        # ***** EOR - Exclusive OR *****
        if opcode == 0x49:  # Immediate, 2, 2
            self.A = self.A ^ self.get_PC_byte()
        elif opcode == 0x45:  # Zero Page, 2, 3
            self.A = self.A ^ self.get_zero_page()
        elif opcode == 0x55:  # Zero Page X, 2, 4
            self.A = self.A ^ self.get_zero_page_x()
        elif opcode == 0x4D:  # Absolute, 3, 4
            self.A = self.A ^ self.get_absolute()
        elif opcode == 0x5D:  # Absolute X, 3, 4 (+1 if page crossed)
            self.A = self.A ^ self.get_absolute_x()
        elif opcode == 0x59:  # Absolute Y, 3, 4 (+1 if page crossed)
            self.A = self.A ^ self.get_absolute_y()
        elif opcode == 0x41:  # Indirect X, 2, 6
            self.A = self.A ^ self.get_indirect_x()
        elif opcode == 0x51:  # Indirect Y, 2, 5 (+1 if page crossed)
            self.A = self.A ^ self.get_indirect_y()
        else:
            return self.invalid_instruction(opcode)

        self.set_Z(self.A == 0)
        self.set_N(self.A >> 7)

    def INC(self, opcode):
        # ***** INC - Increment Memory *****
        if opcode == 0xE6:  # Zero Page, 2, 5
            addr = self.get_zero_page_addr()
        elif opcode == 0xF6:  # Zero Page X, 2, 6
            addr = self.get_zero_page_addr_x()
        elif opcode == 0xEE:  # Absolute, 3, 6
            addr = self.get_absolute_addr()
        elif opcode == 0xFE:  # Absolute X, 3, 7
            addr = self.get_absolute_addr_x()
        else:
            return self.invalid_instruction(opcode)

        result = self.mread(addr) + 1
        self.mwrite(addr, result)
        self.set_Z(result == 0)
        self.set_N(result >> 7)

    def INX(self, opcode):
        # ***** INX - Increment X Register *****
        if opcode == 0xE8:  # Implied, 1, 2
            self.X = self.X + 1
            self.set_Z(self.X == 0)
            self.set_N(self.X >> 7)
        else:
            return self.invalid_instruction(opcode)

    def INY(self, opcode):
        # ***** INY - Increment Y Register *****
        if opcode == 0xC8:  # Implied, 1, 2
            self.Y = self.Y + 1
            self.set_Z(self.Y == 0)
            self.set_N(self.Y >> 7)
        else:
            return self.invalid_instruction(opcode)

    def ISC(self, opcode):
        """****** ISC - illegal *****
          essentially INC + SBC
        """
        print('ISC not implemented')
        # if opcode == 0xEF:

        # elif opcode == 0xFF:
        #     asd
        # elif opcode == 0xFB:
        #     sd
        # elif opcode == 0xE7:
        #     asdf
        # elif opcode == 0xF7:
        #     asdf
        # elif opcode == 0xE3:
        #     asdf
        # elif opcode == 0xF3:

    def JMP(self, opcode):
        # ***** JMP - Jump *****
        if opcode == 0x4C:  # Absolute, 3, 3
            self.PC = self.get_absolute_addr()
        elif opcode == 0x6C:  # Indirect, 3, 5
            self.PC = self.get_indirect()
        else:
            return self.invalid_instruction(opcode)

    def JSR(self, opcode):
        # ***** JSR - Jump to Subroutine *****
        if opcode == 0x20:  # Absolute, 3, 6
            jump_addr = self.get_absolute_addr()
            self.SP -= 2
            bytes_to_load = bytearray([self.PC & 0xFF, self.PC >> 8])
            pointer = self.SP
            for b in bytes_to_load:
                self.mwrite(pointer, b)
                pointer += 1
            self.PC = jump_addr
        else:
            return self.invalid_instruction(opcode)

    def KIL(self, opcode):
        print('KIL not implemented!')

    def LAS(self, opcode):
        print('LAS not implemented')

    def LAX(self, opcode):
        print('LAX not implemented')

    def LDA(self, opcode):
        # ***** LDA - Load Accumulator *****
        if opcode == 0xA9:  # Immediate, 2, 2
            self.A = self.get_PC_byte()
        elif opcode == 0xA5:  # Zero Page, 2, 3
            self.A = self.get_zero_page()
        elif opcode == 0xB5:  # Zero Page X, 2, 4
            self.A = self.get_zero_page_x()
        elif opcode == 0xAD:  # Absolute, 3, 4
            self.A = self.get_absolute()
        elif opcode == 0xBD:  # Absolute X, 3, 4 (+1 if page crossed)
            self.A = self.get_absolute_x()
        elif opcode == 0xB9:  # Absolute Y, 3, 4 (+1 if page crossed)
            self.A = self.get_absolute_y()
        elif opcode == 0xA1:  # Indirect X, 2, 6
            self.A = self.get_indirect_x()
        elif opcode == 0xB1:  # Indirect Y, 2, 5 (+1 if page crossed)
            self.A = self.get_indirect_y()
        else:
            return self.invalid_instruction(opcode)

        self.set_Z(self.A == 0)
        self.set_N(self.A >> 7)

    def LDX(self, opcode):
        # ***** LDX - Load X Register *****
        if opcode == 0xA2:  # Immediate, 2, 2
            self.X = self.get_PC_byte()
        elif opcode == 0xA6:  # Zero Page, 2, 3
            self.X = self.get_zero_page()
        elif opcode == 0xB6:  # Zero Page X, 2, 4
            self.X = self.get_zero_page_x()
        elif opcode == 0xAE:  # Absolute, 3, 4
            self.X = self.get_absolute()
        elif opcode == 0xBE:  # Absolute X, 3, 4 (+1 if page crossed)
            self.X = self.get_absolute_x()
        else:
            return self.invalid_instruction(opcode)

        self.set_Z(self.X == 0)
        self.set_N(self.X >> 7)

    def LDY(self, opcode):
        # ***** LDY - Load Y Register *****
        if opcode == 0xA0:  # Immediate, 2, 2
            self.Y = self.get_PC_byte()
        elif opcode == 0xA4:  # Zero Page, 2, 3
            self.Y = self.get_zero_page()
        elif opcode == 0xB4:  # Zero Page X, 2, 4
            self.Y = self.get_zero_page_x()
        elif opcode == 0xAC:  # Absolute, 3, 4
            self.Y = self.get_absolute()
        elif opcode == 0xBC:  # Absolute X, 3, 4 (+1 if page crossed)
            self.Y = self.get_absolute_x()
        else:
            return self.invalid_instruction(opcode)

        self.set_Z(self.Y == 0)
        self.set_N(self.Y >> 7)

    def LSR(self, opcode):
        # ***** LSR - Logical Shift Right *****
        if opcode == 0x4A:  # Accumulator, 1, 2
            operand = self.A
            result = self.A >> 1
            self.A = result

        else:
            if opcode == 0x46:  # Zero Page, 2, 5
                addr = self.get_zero_page_addr()
            elif opcode == 0x56:  # Zero Page,X, 2, 6
                addr = self.get_zero_page_addr_x()
            elif opcode == 0x4E:  # Absolute, 3, 6
                addr = self.get_absolute_addr()
            elif opcode == 0x5E:  # Absolute,X, 3, 7
                addr = self.get_absolute_addr_x()
            else:
                return self.invalid_instruction(opcode)

            operand = self.mread(addr)
            result = operand >> 1
            self.mwrite(addr, result)

        self.set_C(operand & 0b1)
        self.set_Z(result == 0)
        self.set_N(result >> 7)

    def NOP(self, opcode):
        # ***** NOP - No Operation *****
        # if opcode == 0xEA:  # Implied, 1, 2
        pass
        # else:
        #     return self.invalid_instruction(opcode)

    def ORA(self, opcode):
        # ***** ORA - Logical Inclusive OR *****
        if opcode == 0x09:  # Immediate, 2, 2
            operand = self.get_PC_byte()
        elif opcode == 0x05:  # Zero Page, 2, 3
            operand = self.get_zero_page()
        elif opcode == 0x15:  # Zero Page X, 2, 4
            operand = self.get_zero_page_x()
        elif opcode == 0x0D:  # Absolute, 3, 4
            operand = self.get_absolute()
        elif opcode == 0x1D:  # Absolute X, 3, 4 (+1 if page crossed)
            operand = self.get_absolute_x()
        elif opcode == 0x19:  # Absolute Y, 3, 4 (+1 if page crossed)
            operand = self.get_absolute_y()
        elif opcode == 0x01:  # Indirect X, 2, 6
            operand = self.get_indirect_x()
        elif opcode == 0x11:  # Indirect Y, 2, 5 (+1 if page crossed)
            operand = self.get_indirect_y()
        else:
            return self.invalid_instruction(opcode)

        self.A = self.A | operand
        self.set_Z(self.A == 0)
        self.set_N(self.A >> 7)

    def PHA(self, opcode):
        # ***** PHA - Push Accumulator *****
        if opcode == 0x48:  # Implied, 1, 3
            self.SP -= 1
            self.mwrite(self.SP, self.A)
        else:
            return self.invalid_instruction(opcode)

    def PHP(self, opcode):
        # ***** PHP - Push Processor Status *****
        # if opcode == 0x08:  # Implied, 1, 3
        self.SP -= 1
        # bit 4 is 1 if from PHP
        proc = (self.P % 256) | 0b110000
        self.mwrite(self.SP, proc)
        # else:
        #     return self.invalid_instruction(opcode)

    def PLA(self, opcode):
        # ***** PLA - Pull Accumulator *****
        if opcode == 0x68:  # Implied, 1, 4
            self.A = self.mread(self.SP)
            self.SP += 1
            self.set_Z(self.A == 0)
            self.set_N(self.A >> 7)
        else:
            return self.invalid_instruction(opcode)

    def PLP(self, opcode):
        # ***** PLP - Pull Processor Status *****
        if opcode == 0x28:  # Implied, 1, 4
            self.P = self.mread(self.SP)
            self.set_B(0)
            self.set_bit_5(1)
            self.SP += 1
        else:
            return self.invalid_instruction(opcode)

    def RLA(self, opcode):
        print('RLA not implemented!')

    def ROL(self, opcode):
        # ***** ROL - Rotate Left *****
        if opcode == 0x2A:  # Accumulator, 1, 2
            operand = self.A
            result = (operand << 1) | self.C
            self.A = result
        else:
            if opcode == 0x26:  # Zero Page, 2, 5
                addr = self.get_zero_page_addr()
            elif opcode == 0x36:  # Zero Page X, 2, 6
                addr = self.get_zero_page_addr_x()
            elif opcode == 0x2E:  # Absolute, 3, 6
                addr = self.get_absolute_addr()
            elif opcode == 0x3E:  # Absolute X, 3, 7
                addr = self.get_absolute_addr_x()
            else:
                return self.invalid_instruction(opcode)

            operand = self.mread(addr)
            result = (operand << 1) | self.C
            self.mwrite(addr, result)

        self.set_C(operand >> 7)
        self.set_Z(self.A == 0)
        self.set_N(result >> 7)

    def ROR(self, opcode):
        # ***** ROR - Rotate Right *****
        if opcode == 0x6A:  # Accumulator, 1, 2
            operand = self.A
            result = (operand >> 1) | (self.C << 7)
            self.A = result
        else:
            if opcode == 0x66:  # Zero Page, 2, 5
                addr = self.get_zero_page_addr()
            elif opcode == 0x76:  # Zero Page X, 2, 6
                addr = self.get_zero_page_addr_x()
            elif opcode == 0x6E:  # Absolute, 3, 6
                addr = self.get_absolute_addr()
            elif opcode == 0x7E:  # Absolute X, 3, 7
                addr = self.get_absolute_addr_x()
            else:
                return self.invalid_instruction(opcode)

            operand = self.mread(addr)
            result = (operand >> 1) | (self.C << 7)
            self.mwrite(addr, result)

        self.set_C(operand & 0b1)
        self.set_Z(self.A == 0)
        self.set_N(result >> 7)

    def RRA(self, opcode):
        print('RRA not implemented!')

    def RTI(self, opcode):
        # ***** RTI - Return from Interrupt *****
        if opcode == 0x40:  # Implied, 1, 6
            # loaded = self.ram.mem_get(self.SP, 3)
            loaded = []
            for i in range(3):
                loaded.append(self.mread(self.SP + i))
            self.P = loaded[0]
            lower = loaded[1]
            upper = loaded[2]
            self.PC = (upper << 8) | (lower & 0xFF)
            self.SP += 3
        else:
            return self.invalid_instruction(opcode)

    def RTS(self, opcode):
        # ***** RTS - Return from Subroutine *****
        if opcode == 0x60:  # Implied, 1, 6
            # loaded = self.ram.mem_get(self.SP, 2)
            loaded = []
            for i in range(2):
                loaded.append(self.mread(self.SP + i))
            lower = loaded[0]
            upper = loaded[1]
            self.PC = (upper << 8) | lower
            self.SP += 2
        else:
            return self.invalid_instruction(opcode)

    def SAX(self, opcode):
        print('SAX not implemented')

    def SBC(self, opcode):
        # ***** SBC - Subtract with Carry *****
        if opcode == 0xE9:  # Immediate, 2, 2
            operand = self.get_PC_byte();
        elif opcode == 0xE5:  # Zero Page, 2, 3
            operand = self.get_zero_page_x()
        elif opcode == 0xF5:  # Zero Page X, 2, 4
            operand = self.get_zero_page_x()
        elif opcode == 0xED:  # Absolute, 3, 4
            operand = self.get_absolute()
        elif opcode == 0xFD:  # Absolute X, 3, 4 (+1 if page crossed)
            operand = self.get_absolute_x()
        elif opcode == 0xF9:  # Absolute Y, 3, 4 (+1 if page crossed)
            operand = self.get_absolute_y()
        elif opcode == 0xE1:  # Indirect X, 2, 6
            operand = self.get_indirect_x()
        elif opcode == 0xF1:  # Indirect Y, 2, 5 (+1 if page crossed)
            operand = self.get_indirect_y()
        else:
            return self.invalid_instruction(opcode)

        old_A = self.A
        result = self.A - operand - (1 - self.C)
        self.A = result & 0xFF

        self.set_C(1 - (result >> 8))
        self.set_Z(self.A == 0)
        self.set_N(self.A >> 7)

        if (old_A >> 7 != operand >> 7) and (self.A >> 7 != old_A >> 7):
            self.set_V(1)
        else:
            self.set_V(0)

    def SEC(self, opcode):
        # ***** SEC - Set Carry Flag *****
        if opcode == 0x38:  # Implied, 1, 2
            self.set_C(1)
        else:
            return self.invalid_instruction(opcode)

    def SED(self, opcode):
        # ***** SED - Set Decimal Flag *****
        if opcode == 0xF8:  # Implied, 1, 2
            self.set_D(1)
        else:
            return self.invalid_instruction(opcode)

    def SEI(self, opcode):
        # ***** SEI - Set Interrupt Disable *****
        # if opcode == 0x78:  # Implied, 1, 2
        self.set_I(1)
        # else:
        #   return self.invalid_instruction(opcode)

    def SKW(self, opcode):
        """***** SKW - Skip Next Word *****
        this opcode performs a read, but doesn't
        actually do anything with the value lol 
        important for how many cycles to add though
        especially if the page is crossed

        """
        if opcode == 0x0C:
            self.get_absolute_addr()
        else:
            self.get_absolute_addr_x()

    def SLO(self, opcode):
        print('SLO not implemented!')

    def SRE(self, opcode):
        print('SRE not implemented!')

    def SHX(self, opcode):
        print('SHX not implemented')

    def SHY(self, opcode):
        print('SHY not implemented')

    def STA(self, opcode):
        # ***** STA - Store Accumulator *****
        if opcode == 0x85:  # Zero Page, 2, 3
            addr = self.get_zero_page_addr()
        elif opcode == 0x95:  # Zero Page X, 2, 4
            addr = self.get_zero_page_addr_x()
        elif opcode == 0x8D:  # Absolute, 3, 4
            addr = self.get_absolute_addr()
        elif opcode == 0x9D:  # Absolute X, 3, 5
            addr = self.get_absolute_addr_x()
        elif opcode == 0x99:  # Absolute Y, 3, 5
            addr = self.get_absolute_addr_y()
        elif opcode == 0x81:  # Indirect X, 2, 6
            addr = self.get_indirect_addr_x()
        elif opcode == 0x91:  # Indirect Y, 2, 6
            addr = self.get_indirect_addr_y()
        else:
            return self.invalid_instruction(opcode)

        self.mwrite(addr, self.A)

    def STX(self, opcode):
        # ***** STX - Store X Register *****
        if opcode == 0x86:  # Zero Page, 2, 3
            addr = self.get_zero_page_addr()
        elif opcode == 0x96:  # Zero Page Y, 2, 4
            addr = self.get_zero_page_addr_y()
        elif opcode == 0x8E:  # Absolute, 3, 4
            addr = self.get_absolute_addr()
        else:
            return self.invalid_instruction(opcode)

        self.mwrite(addr, self.X)

    def STY(self, opcode):
        # ***** STY - Store Y Register *****
        if opcode == 0x84:  # Zero Page, 2, 3
            addr = self.get_zero_page_addr()
        elif opcode == 0x94:  # Zero Page X, 2, 4
            addr = self.get_zero_page_addr_x()
        elif opcode == 0x8C:  # Absolute, 3, 4
            addr = self.get_absolute_addr()
        else:
            return self.invalid_instruction(opcode)

        self.mwrite(addr, self.Y)

    def TAS(self, opcode):
        print('TAS not implemented')

    def TAX(self, opcode):
        # ***** TAX - Transfer Accumulator to X *****
        if opcode == 0xAA:  # Implied, 1, 2
            self.X = self.A
            self.set_Z(self.X == 0)
            self.set_N(self.X >> 7)
        else:
            return self.invalid_instruction(opcode)

    def TAY(self, opcode):
        # ***** TAY - Transfer Accumulator to Y *****
        if opcode == 0xA8:  # Implied, 1, 2
            self.Y = self.A
            self.set_Z(self.Y == 0)
            self.set_N(self.Y >> 7)
        else:
            return self.invalid_instruction(opcode)

    def TSX(self, opcode):
        # ***** TSX - Transfer Stack Pointer to X *****
        if opcode == 0xBA:  # Implied, 1, 2
            self.X = self.SP
            self.set_Z(self.X == 0)
            self.set_N(self.X >> 7)
        else:
            return self.invalid_instruction(opcode)

    def TXA(self, opcode):
        # ***** TXA - Transfer X to Accumulator *****
        if opcode == 0x8A:  # Implied, 1, 2
            self.A = self.X
            self.set_Z(self.A == 0)
            self.set_N(self.A >> 7)
        else:
            return self.invalid_instruction(opcode)

    def TXS(self, opcode):
        # ***** TXS - Transfer X to Stack Pointer *****
        if opcode == 0x9A:  # Implied, 1, 2
            self.SP = self.X
        else:
            return self.invalid_instruction(opcode)

    def TYA(self, opcode):
        # ***** TYA - Transfer Y to Accumulator *****
        if opcode == 0x98:  # Implied, 1, 2
            self.A = self.Y
            self.set_Z(self.A == 0)
            self.set_N(self.A >> 7)
        else:
            return self.invalid_instruction(opcode)

    def XAA(self, opcode):
        print('XAA not implemented')

    def invalid_instruction(self, opcode):
        print("Invalid instruction: " + hex(opcode))
        raise Exception

    @property
    def C(self):
        return self.get_bit_P(0)

    @property
    def Z(self):
        return self.get_bit_P(1)

    @property
    def I(self):
        return self.get_bit_P(2)

    @property
    def D(self):
        return self.get_bit_P(3)

    @property
    def B(self):
        return self.get_bit_P(4)

    @property
    def V(self):
        return self.get_bit_P(6)

    @property
    def N(self):
        return self.get_bit_P(7)

    # TODO: change these to setters
    def set_C(self, bit):
        self.set_bit_P(0, bit)

    def set_Z(self, bit):
        self.set_bit_P(1, bit)

    def set_I(self, bit):
        self.set_bit_P(2, bit)

    def set_D(self, bit):
        self.set_bit_P(3, bit)

    def set_B(self, bit):
        self.set_bit_P(4, bit)

    def set_bit_5(self, bit):
        self.set_bit_P(5, bit)

    def set_V(self, bit):
        self.set_bit_P(6, bit)

    def set_N(self, bit):
        self.set_bit_P(7, bit)

    def set_bit_P(self, pos, bit):
        mask = ~(1 << pos)
        self.P = self.P & mask | (bit << pos)

    def get_bit_P(self, pos):
        return self.get_bit(self.P, pos)

    def get_bit(self, target, pos):
        return (target >> pos) & 0b1

    def convert_8bit_twos(self, num):
        if (num & (1 << 7)):
            return -((num ^ 0xFF) + 1)
        else:
            return num

    def create_opcode_table(self):
        self.opcode_to_instruction = [
            self.BRK, self.ORA, self.KIL, self.SLO, self.NOP, self.ORA, self.ASL, self.SLO, self.PHP, self.ORA,
            self.ASL, self.ANC, self.NOP, self.ORA, self.ASL, self.SLO,
            self.BPL, self.ORA, self.KIL, self.SLO, self.NOP, self.ORA, self.ASL, self.SLO, self.CLC, self.ORA,
            self.NOP, self.SLO, self.NOP, self.ORA, self.ASL, self.SLO,
            self.JSR, self.AND, self.KIL, self.RLA, self.BIT, self.AND, self.ROL, self.RLA, self.PLP, self.AND,
            self.ROL, self.ANC, self.BIT, self.AND, self.ROL, self.RLA,
            self.BMI, self.AND, self.KIL, self.RLA, self.NOP, self.AND, self.ROL, self.RLA, self.SEC, self.AND,
            self.NOP, self.RLA, self.NOP, self.AND, self.ROL, self.RLA,
            self.RTI, self.EOR, self.KIL, self.SRE, self.NOP, self.EOR, self.LSR, self.SRE, self.PHA, self.EOR,
            self.LSR, self.ALR, self.JMP, self.EOR, self.LSR, self.SRE,
            self.BVC, self.EOR, self.KIL, self.SRE, self.NOP, self.EOR, self.LSR, self.SRE, self.CLI, self.EOR,
            self.NOP, self.SRE, self.NOP, self.EOR, self.LSR, self.SRE,
            self.RTS, self.ADC, self.KIL, self.RRA, self.NOP, self.ADC, self.ROR, self.RRA, self.PLA, self.ADC,
            self.ROR, self.ARR, self.JMP, self.ADC, self.ROR, self.RRA,
            self.BVS, self.ADC, self.KIL, self.RRA, self.NOP, self.ADC, self.ROR, self.RRA, self.SEI, self.ADC,
            self.NOP, self.RRA, self.NOP, self.ADC, self.ROR, self.RRA,
            self.NOP, self.STA, self.NOP, self.SAX, self.STY, self.STA, self.STX, self.SAX, self.DEY, self.NOP,
            self.TXA, self.XAA, self.STY, self.STA, self.STX, self.SAX,
            self.BCC, self.STA, self.KIL, self.AHX, self.STY, self.STA, self.STX, self.SAX, self.TYA, self.STA,
            self.TXS, self.TAS, self.SHY, self.STA, self.SHX, self.AHX,
            self.LDY, self.LDA, self.LDX, self.LAX, self.LDY, self.LDA, self.LDX, self.LAX, self.TAY, self.LDA,
            self.TAX, self.LAX, self.LDY, self.LDA, self.LDX, self.LAX,
            self.BCS, self.LDA, self.KIL, self.LAX, self.LDY, self.LDA, self.LDX, self.LAX, self.CLV, self.LDA,
            self.TSX, self.LAS, self.LDY, self.LDA, self.LDX, self.LAX,
            self.CPY, self.CMP, self.NOP, self.DCP, self.CPY, self.CMP, self.DEC, self.DCP, self.INY, self.CMP,
            self.DEX, self.AXS, self.CPY, self.CMP, self.DEC, self.DCP,
            self.BNE, self.CMP, self.KIL, self.DCP, self.NOP, self.CMP, self.DEC, self.DCP, self.CLD, self.CMP,
            self.NOP, self.DCP, self.NOP, self.CMD, self.DEC, self.DCP,
            self.CPX, self.SBC, self.NOP, self.ISC, self.CPX, self.SBC, self.INC, self.ISC, self.INX, self.SBC,
            self.NOP, self.SBC, self.CPX, self.SBC, self.INC, self.ISC,
            self.BEQ, self.SBC, self.KIL, self.ISC, self.NOP, self.SBC, self.INC, self.ISC, self.SED, self.SBC,
            self.NOP, self.ISC, self.NOP, self.SBC, self.INC, self.ISC
        ]

    # Prints contents of registers
    def _cpu_dump(self, PC, f):
        PC_str = shex(PC).rjust(4, '0')
        A_str = shex(self.A).rjust(2, '0')
        X_str = shex(self.X).rjust(2, '0')
        Y_str = shex(self.Y).rjust(2, '0')
        P_str = shex(self.P).rjust(2, '0')
        SP_str = shex(self.SP).rjust(2, '0')
        cycles = str(self.elapsed_cycles - 1).rjust(3, ' ')
        vals = (shex(self.mread(PC)).rjust(2, '0'),
                shex(self.mread(PC + 1)).rjust(2, '0'),
                shex(self.mread(PC + 2)).rjust(2, '0'))

        return "{}    {}    A:{} X:{} Y:{} P:{} SP:{} CYC:{}".format(PC_str, f.__name__, A_str, X_str, Y_str, P_str,
                                                                     SP_str, cycles)

        # return "{}  {} {} {}  {}         A:{} X:{} Y:{} P:{} SP:{} CYC:{}".format(PC_str, vals[0], vals[1], vals[2], f.__name__, A_str, X_str, Y_str, P_str, SP_str, cycles)

    @property
    def A(self):
        return self.reg["A"][0]

    @A.setter
    def A(self, value):
        self.reg["A"][0] = value % 256

    @property
    def X(self) -> bytes:
        return self.reg["X"][0]

    @X.setter
    def X(self, value) -> None:
        self.reg["X"][0] = value % 256

    @property
    def Y(self) -> bytes:
        return self.reg["Y"][0]

    @Y.setter
    def Y(self, value) -> None:
        self.reg["Y"][0] = value % 256


# mapping from opcode to num_cycles
instruction_cycles = [7, 6, 2, 8, 3, 3, 5, 5, 3, 2, 2, 2, 4, 4, 6, 6,
                      2, 5, 2, 8, 4, 4, 6, 6, 2, 4, 2, 7, 4, 4, 7, 7,
                      6, 6, 2, 8, 3, 3, 5, 5, 4, 2, 2, 2, 4, 4, 6, 6,
                      2, 5, 2, 8, 4, 4, 6, 6, 2, 4, 2, 7, 4, 4, 7, 7,
                      6, 6, 2, 8, 3, 3, 5, 5, 3, 2, 2, 2, 3, 4, 6, 6,
                      2, 5, 2, 8, 4, 4, 6, 6, 2, 4, 2, 7, 4, 4, 7, 7,
                      6, 6, 2, 8, 3, 3, 5, 5, 4, 2, 2, 2, 5, 4, 6, 6,
                      2, 5, 2, 8, 4, 4, 6, 6, 2, 4, 2, 7, 4, 4, 7, 7,
                      2, 6, 2, 6, 3, 3, 3, 3, 2, 2, 2, 2, 4, 4, 4, 4,
                      2, 6, 2, 6, 4, 4, 4, 4, 2, 5, 2, 5, 5, 5, 5, 5,
                      2, 6, 2, 6, 3, 3, 3, 3, 2, 2, 2, 2, 4, 4, 4, 4,
                      2, 5, 2, 5, 4, 4, 4, 4, 2, 4, 2, 4, 4, 4, 4, 4,
                      2, 6, 2, 8, 3, 3, 5, 5, 2, 2, 2, 2, 4, 4, 6, 6,
                      2, 5, 2, 8, 4, 4, 6, 6, 2, 4, 2, 7, 4, 4, 7, 7,
                      2, 6, 2, 8, 3, 3, 5, 5, 2, 2, 2, 2, 4, 4, 6, 6,
                      2, 5, 2, 8, 4, 4, 6, 6, 2, 4, 2, 7, 4, 4, 7, 7]

# how many cycles when a page is crossed
instruction_page_cycles = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                           1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0,
                           0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                           1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0,
                           0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                           1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0,
                           0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                           1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0,
                           0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                           1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                           0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                           1, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 1,
                           0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                           1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0,
                           0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                           1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0]
