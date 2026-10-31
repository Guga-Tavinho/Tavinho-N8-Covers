// Ghidra headless script: label NES regs, disassemble from vectors, dump listing + decompilation.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.mem.*;
import java.io.*;

public class DumpNES extends GhidraScript {
    @Override
    public void run() throws Exception {
        String outDir = getScriptArgs()[0];
        AddressSpace sp0 = null;
        Memory mem = currentProgram.getMemory();
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
        String[][] regs = {{"PPUCTRL","2000"},{"PPUMASK","2001"},{"PPUSTATUS","2002"},{"OAMADDR","2003"},
            {"OAMDATA","2004"},{"PPUSCROLL","2005"},{"PPUADDR","2006"},{"PPUDATA","2007"},
            {"OAMDMA","4014"},{"APU_STATUS","4015"},{"JOY1","4016"},{"JOY2","4017"}};
        if (mem.getBlock(sp.getAddress(0)) == null) {
            mem.createUninitializedBlock("RAM", sp.getAddress(0), 0x800, false);
            mem.createUninitializedBlock("PPU", sp.getAddress(0x2000), 8, false);
            mem.createUninitializedBlock("APUIO", sp.getAddress(0x4000), 0x20, false);
            mem.createUninitializedBlock("EXP", sp.getAddress(0x4020), 0x3FE0, false);
        }
        for (String[] r : regs) createLabel(sp.getAddress(Long.parseLong(r[1],16)), r[0], true);
        String[] vn = {"NMI","RESET","IRQ"};
        for (int i = 0; i < 3; i++) {
            Address va = sp.getAddress(0xFFFA + 2*i);
            int t = (mem.getByte(va) & 0xff) | ((mem.getByte(va.add(1)) & 0xff) << 8);
            Address ta = sp.getAddress(t);
            disassemble(ta);
            createFunction(ta, vn[i]);
        }
        analyzeAll(currentProgram);
        java.io.File nf = new java.io.File(getScriptArgs()[1]);
        for (String line : java.nio.file.Files.readAllLines(nf.toPath())) {
            line = line.trim(); if (line.isEmpty() || line.startsWith("#")) continue;
            String[] p = line.split("\s+");
            Address a = sp.getAddress(Long.parseLong(p[0],16));
            Function fn = getFunctionAt(a);
            if (fn == null) fn = createFunction(a, p[1]);
            if (fn != null) fn.setName(p[1], SourceType.USER_DEFINED);
        }
        String[][] vars = {{"c_sp","28"},{"sreg","2a"},{"regsave","2c"},{"ptr1","30"},{"ptr2","32"},{"ptr3","34"},{"ptr4","36"},{"tmp1","38"},
            {"txt_ptr","92"},{"ppu_src","9a"},{"ppu_dst","9c"},{"nmi_flag","9e"},{"txt_color","9f"},{"joy_cur","a0"},{"nmi_busy","a2"},
            {"sel_index_lo","8259"},{"sel_index_hi","825a"},{"bg_palette","825f"},{"EDREG_INDEX","4400"},{"EDREG_DATA","4401"},
            {"bios_api_table_src","fc00"},{"bios_api_table","4a9"},{"heap_ptr","4e9"},{"dir_sort_table_ptr","4ff"},{"name_buf_ptr","501"},
            {"dir_count","552"},{"joy_state","51d"}};
        for (String[] v : vars) createLabel(sp.getAddress(Long.parseLong(v[1],16)), v[0], true);
        PrintWriter asm = new PrintWriter(new File(outDir, "listing.asm"), "UTF-8");
        for (Instruction ins : currentProgram.getListing().getInstructions(true)) {
            Function f = getFunctionContaining(ins.getAddress());
            Symbol s = getSymbolAt(ins.getAddress());
            if (s != null) asm.println(s.getName() + ":");
            String cmt = "";
            for (Reference rf : ins.getReferencesFrom()) {
                Symbol ts = getSymbolAt(rf.getToAddress());
                if (ts != null && !ts.getName().startsWith("LAB_")) cmt = "   ; " + ts.getName();
            }
            asm.println(String.format("  %s  %-10s %-24s%s", ins.getAddress(), bytesHex(ins), ins.toString(), cmt));
        }
        asm.close();
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        PrintWriter c = new PrintWriter(new File(outDir, "decompiled.c"), "UTF-8");
        PrintWriter fl = new PrintWriter(new File(outDir, "functions.txt"), "UTF-8");
        for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
            StringBuilder callers = new StringBuilder();
            for (Function cf : f.getCallingFunctions(monitor)) callers.append(cf.getEntryPoint()).append(' ');
            fl.println(f.getEntryPoint() + "  " + f.getName() + "  size=" + f.getBody().getNumAddresses() + "  callers: " + callers);
            DecompileResults r = di.decompileFunction(f, 60, monitor);
            c.println("// ===== " + f.getName() + " @ " + f.getEntryPoint());
            c.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// decompile failed: " + r.getErrorMessage());
        }
        c.close(); fl.close();
        PrintWriter xr = new PrintWriter(new File(outDir, "xrefs_io.txt"), "UTF-8");
        long[][] ranges = {{0x2000,0x2008},{0x4000,0x4020},{0x4020,0x8000}};
        for (long[] rg : ranges) for (long a = rg[0]; a < rg[1]; a++) {
            Address ad = sp.getAddress(a);
            for (Reference ref : getReferencesTo(ad)) {
                Function f = getFunctionContaining(ref.getFromAddress());
                xr.println(String.format("%04X <- %s %s (%s)", a, ref.getFromAddress(), ref.getReferenceType(), f == null ? "?" : f.getName()));
            }
        }
        xr.close();
    }
    String bytesHex(Instruction ins) throws Exception {
        StringBuilder sb = new StringBuilder();
        for (byte b : ins.getBytes()) sb.append(String.format("%02X", b & 0xff));
        return sb.toString();
    }
}
