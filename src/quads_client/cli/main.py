import sys
from quads_client.shell import QuadsClientShell


def main():
    """
    Main entry point for quads-client.

    Supports three modes:
    - Interactive mode: quads-client
    - One-shot mode: quads-client <command>
    - Piped mode: echo 'command' | quads-client

    A global --debug/-d flag enables HTTP request/response tracing to stderr
    (equivalent to 'set debug true' in interactive mode).
    """
    argv = sys.argv[1:]
    debug = False
    if argv and argv[0] in ("--debug", "-d"):
        argv = argv[1:]
        debug = True

    is_oneshot = len(argv) > 0
    is_piped = not sys.stdin.isatty()

    shell = QuadsClientShell(quiet=is_oneshot or is_piped)
    if debug:
        shell.debug = True

    if is_oneshot:
        cmd_str = " ".join(argv)
        exit_code = shell.execute_oneshot_command(cmd_str)
        sys.exit(exit_code)
    elif is_piped:
        exit_code = 0
        for line in sys.stdin:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            result = shell.execute_oneshot_command(line)
            if result != 0:
                exit_code = result
        sys.exit(exit_code)
    else:
        shell.cmdloop()


if __name__ == "__main__":
    main()
