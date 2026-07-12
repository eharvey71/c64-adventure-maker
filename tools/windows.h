/* ------------------------------------------------------------------
   Minimal POSIX shim for StoryTllrC64's script_compiler (macOS/Linux)
   Maps the small set of WinAPI calls used by minilib.h onto stdio.
   Drop this file somewhere and build with:  -I<this dir>
   ------------------------------------------------------------------ */
#ifndef _POSIX_WINDOWS_SHIM_H
#define _POSIX_WINDOWS_SHIM_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include <limits.h>
#include <sys/stat.h>
#include <sys/types.h>

/* selects the portable C code paths in hupack.c */
#ifndef WIN32
#define WIN32 1
#endif

typedef void*          HANDLE;
typedef unsigned int   DWORD;
typedef void*          LPVOID;
typedef const void*    LPCVOID;
typedef int            BOOL;
typedef unsigned char  BYTE;
typedef unsigned short WORD;
typedef unsigned int   UINT;
typedef struct { DWORD dwLowDateTime, dwHighDateTime; } FILETIME;

#define GENERIC_READ            0x80000000
#define GENERIC_WRITE           0x40000000
#define FILE_SHARE_READ         0x00000001
#define CREATE_ALWAYS           2
#define OPEN_EXISTING           3
#define FILE_ATTRIBUTE_NORMAL   0x80
#define INVALID_HANDLE_VALUE    ((HANDLE)-1)
#define TRUE  1
#define FALSE 0
#define MAX_PATH 1024
#define _inline static inline

#ifndef max
#define max(a,b) ((a)>(b)?(a):(b))
#endif
#ifndef min
#define min(a,b) ((a)<(b)?(a):(b))
#endif
#define LOBYTE(w) ((BYTE)((w) & 0xff))
#define HIBYTE(w) ((BYTE)(((w) >> 8) & 0xff))
#ifndef stricmp
#define stricmp  strcasecmp
#endif
#ifndef strnicmp
#define strnicmp strncasecmp
#endif
#ifndef strcmpi
#define strcmpi  strcasecmp
#endif

static inline HANDLE CreateFileA(const char* name, DWORD access, DWORD share,
                                 void* sec, DWORD disp, DWORD flags, void* tmpl)
{
    (void)share;(void)sec;(void)flags;(void)tmpl;
    const char* mode;
    if (disp == CREATE_ALWAYS)       mode = "wb+";
    else if (access & GENERIC_WRITE) mode = "rb+";
    else                             mode = "rb";
    /* translate Windows path separators from scripts to POSIX */
    char fixed[MAX_PATH];
    size_t i;
    for (i = 0; name[i] && i < MAX_PATH-1; i++)
        fixed[i] = (name[i] == '\\') ? '/' : name[i];
    fixed[i] = 0;
    FILE* f = fopen(fixed, mode);
    return f ? (HANDLE)f : INVALID_HANDLE_VALUE;
}

static inline BOOL CloseHandle(HANDLE h)
{
    if (h == INVALID_HANDLE_VALUE || h == NULL) return FALSE;
    return fclose((FILE*)h) == 0;
}

static inline BOOL WriteFile(HANDLE h, LPCVOID buf, DWORD n, DWORD* written, void* ov)
{
    (void)ov;
    size_t w = fwrite(buf, 1, n, (FILE*)h);
    if (written) *written = (DWORD)w;
    return w == n;
}

static inline BOOL ReadFile(HANDLE h, LPVOID buf, DWORD n, DWORD* readn, void* ov)
{
    (void)ov;
    size_t r = fread(buf, 1, n, (FILE*)h);
    if (readn) *readn = (DWORD)r;
    return TRUE;
}

static inline DWORD GetFileSize(HANDLE h, DWORD* hi)
{
    if (hi) *hi = 0;
    FILE* f = (FILE*)h;
    long cur = ftell(f);
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, cur, SEEK_SET);
    return (DWORD)sz;
}

static inline BOOL CreateDirectoryA(const char* path, void* sec)
{
    (void)sec;
    return mkdir(path, 0755) == 0;
}

static inline BOOL GetFileTime(HANDLE h, FILETIME* c, FILETIME* a, FILETIME* w)
{
    (void)h;(void)c;(void)a;
    if (w) { w->dwLowDateTime = 0; w->dwHighDateTime = 0; }
    return TRUE;
}

/* Always report "source newer" so rebuilds are never skipped */
static inline int CompareFileTime(const FILETIME* a, const FILETIME* b)
{
    (void)a;(void)b; return 1;
}

/* Wrap fopen globally so stb_image and friends also get
   Windows->POSIX path separator translation. */
static inline FILE* posix_fopen_slash(const char* name, const char* mode)
{
    char fixed[MAX_PATH];
    size_t i;
    for (i = 0; name[i] && i < MAX_PATH-1; i++)
        fixed[i] = (name[i] == '\\') ? '/' : name[i];
    fixed[i] = 0;
    return (fopen)(fixed, mode);
}
#define fopen(n,m) posix_fopen_slash((n),(m))

#endif /* _POSIX_WINDOWS_SHIM_H */
