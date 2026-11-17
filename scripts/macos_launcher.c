/* Native Apple-silicon entry point; service orchestration stays in Python. */
#include <mach-o/dyld.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
    char executable[PATH_MAX], root[PATH_MAX], python[PATH_MAX], script[PATH_MAX];
    uint32_t size = sizeof(executable);
    if (_NSGetExecutablePath(executable, &size) != 0 || realpath(executable, root) == NULL) return 1;
    for (int i=0;i<4;i++) {
        char *slash = strrchr(root, '/');
        if (!slash) return 1;
        *slash = '\0';
    }
    if (snprintf(python,sizeof(python),"%s/.venv/bin/python",root) >= sizeof(python)) return 1;
    if (snprintf(script,sizeof(script),"%s/scripts/start_local.py",root) >= sizeof(script)) return 1;
    if (chdir(root) != 0) return 1;
    char *args[] = {python,script,argc > 1 && strcmp(argv[1], "--no-open") == 0 ? "--no-open" : NULL,NULL};
    execv(python,args);
    perror("Could not start Thesis Monitor");
    return 1;
}
