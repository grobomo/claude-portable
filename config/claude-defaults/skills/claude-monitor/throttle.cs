using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

class Throttle {
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool SetProcessInformation(IntPtr hProcess, int c, IntPtr i, int s);
    [DllImport("ntdll.dll")] static extern int NtSuspendProcess(IntPtr h);
    [DllImport("ntdll.dll")] static extern int NtResumeProcess(IntPtr h);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr CreateJobObject(IntPtr a, string n);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProc);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool SetInformationJobObject(IntPtr hJob, int cls, IntPtr info, int len);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetProcessIoCounters(IntPtr hProcess, out IO_COUNTERS counters);

    [StructLayout(LayoutKind.Sequential)]
    struct PWR { public uint Version; public uint ControlMask; public uint StateMask; }
    [StructLayout(LayoutKind.Sequential)]
    struct CPURATE { public uint ControlFlags; public uint CpuRate; }
    [StructLayout(LayoutKind.Sequential)]
    struct IO_COUNTERS {
        public ulong ReadOperationCount; public ulong WriteOperationCount; public ulong OtherOperationCount;
        public ulong ReadTransferCount; public ulong WriteTransferCount; public ulong OtherTransferCount;
    }

    static int Main(string[] args) {
        if (args.Length < 2) { ShowUsage(); return 1; }
        string target = args[0].ToLower();
        string action = args[1].ToLower();
        string extra = args.Length > 2 ? args[2] : "";
        int[] pids;
        if (target == "all") {
            var procs = Process.GetProcessesByName("claude");
            pids = new int[procs.Length];
            for (int i = 0; i < procs.Length; i++) pids[i] = procs[i].Id;
        } else { pids = new int[] { int.Parse(target) }; }
        int ok = 0, fail = 0;
        foreach (int pid in pids) {
            try { DoAction(pid, action, extra); ok++; }
            catch (Exception ex) { W("FAIL: PID " + pid + " -> " + ex.Message); fail++; }
        }
        W("Done: " + ok + " ok, " + fail + " failed");
        return fail > 0 ? 1 : 0;
    }

    static void W(string s) { Console.WriteLine(s); }

    static void ShowUsage() {
        W("Usage: throttle.exe <pid|all> <action> [value]");
        W("  cap <pct>   CPU hard cap via Job Object (stays responsive)");
        W("  uncap       Remove CPU cap");
        W("  suspend/resume   Freeze/unfreeze");
        W("  idle/normal/throttle/unthrottle   Priority+EcoQoS");
        W("  status      Show info");
    }

    static void DoAction(int pid, string action, string extra) {
        Process p = Process.GetProcessById(pid);
        switch (action) {
            case "idle": p.PriorityClass = ProcessPriorityClass.Idle; W("OK: PID " + pid + " -> Idle"); break;
            case "belownormal": p.PriorityClass = ProcessPriorityClass.BelowNormal; W("OK: PID " + pid + " -> BelowNormal"); break;
            case "normal": p.PriorityClass = ProcessPriorityClass.Normal; W("OK: PID " + pid + " -> Normal"); break;
            case "eco": SetEco(p.Handle, true); W("OK: PID " + pid + " -> EcoQoS ON"); break;
            case "noeco": SetEco(p.Handle, false); W("OK: PID " + pid + " -> EcoQoS OFF"); break;
            case "throttle": p.PriorityClass = ProcessPriorityClass.Idle; SetEco(p.Handle, true); W("OK: PID " + pid + " -> THROTTLED"); break;
            case "unthrottle": p.PriorityClass = ProcessPriorityClass.Normal; SetEco(p.Handle, false); W("OK: PID " + pid + " -> UNTHROTTLED"); break;
            case "suspend": int sr = NtSuspendProcess(p.Handle); W(sr == 0 ? "OK: PID " + pid + " -> SUSPENDED" : "FAIL: " + sr); break;
            case "resume": int rr = NtResumeProcess(p.Handle); W(rr == 0 ? "OK: PID " + pid + " -> RESUMED" : "FAIL: " + rr); break;
            case "cap": SetCpuCap(p.Handle, pid, extra != "" ? int.Parse(extra) : 5); break;
            case "uncap": SetCpuCap(p.Handle, pid, 0); break;
            case "status": W("PID " + pid + ": pri=" + p.PriorityClass + " RAM=" + (p.WorkingSet64/1048576) + "MB thr=" + p.Threads.Count); break;
            default: throw new Exception("Unknown action: " + action);
        }
    }

    static void SetEco(IntPtr h, bool on) {
        var s = new PWR(); s.Version = 1; s.ControlMask = 4; s.StateMask = on ? (uint)4 : 0;
        int sz = Marshal.SizeOf(s); IntPtr p = Marshal.AllocHGlobal(sz);
        Marshal.StructureToPtr(s, p, false);
        bool r = SetProcessInformation(h, 4, p, sz); Marshal.FreeHGlobal(p);
        if (!r) throw new Exception("SetProcessInformation err " + Marshal.GetLastWin32Error());
    }

    static void SetCpuCap(IntPtr hProc, int pid, int pct) {
        IntPtr hJob = CreateJobObject(IntPtr.Zero, "ClaudeThrottle_" + pid);
        if (hJob == IntPtr.Zero) { W("FAIL: CreateJobObject err " + Marshal.GetLastWin32Error()); return; }
        var info = new CPURATE();
        if (pct > 0) { info.ControlFlags = 0x1 | 0x4; info.CpuRate = (uint)(pct * 100); }
        else { info.ControlFlags = 0x1 | 0x4; info.CpuRate = 10000; }
        int sz = Marshal.SizeOf(info); IntPtr ptr = Marshal.AllocHGlobal(sz);
        Marshal.StructureToPtr(info, ptr, false);
        bool setOk = SetInformationJobObject(hJob, 15, ptr, sz); Marshal.FreeHGlobal(ptr);
        if (!setOk) { int e = Marshal.GetLastWin32Error(); CloseHandle(hJob); W("FAIL: SetInfo err " + e); return; }
        bool aOk = AssignProcessToJobObject(hJob, hProc);
        if (!aOk) { int e = Marshal.GetLastWin32Error(); CloseHandle(hJob); W("FAIL: Assign err " + e + " (already in job?)"); return; }
        W(pct > 0 ? "OK: PID " + pid + " -> CPU capped at " + pct + "%" : "OK: PID " + pid + " -> CPU cap REMOVED");
    }
}