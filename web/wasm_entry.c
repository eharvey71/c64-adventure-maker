/* Web entry point for StoryTllr's compiler.
 * main.c is built with -Dmain=storytllr_main, so the compiler's command-line
 * main becomes an ordinary function the page can call with file names. */
#include <emscripten.h>
int storytllr_main(int argc, const char *argv[]);

EMSCRIPTEN_KEEPALIVE
int compile_game(const char *script, const char *header, const char *cartridge)
{
    const char *argv[] = {"script_compiler", script, header, cartridge, 0};
    return storytllr_main(4, argv);
}
