#include <stdint.h>
#include "chezscheme.h"
#include "racketcs.h"
#ifdef SECOND_BRIDGE
#define INITIALIZER second_bind
#define ANSWER second_answer
#else
#define INITIALIZER first_init
#define ANSWER first_answer
#endif
static ptr procedure;
int INITIALIZER(void) {
#ifndef SECOND_BRIDGE
  static char *arguments[] = {"-n", "-A", RACKET_ADDON_DIR,
                             "-G", RACKET_CONFIG_DIR,
                             "-X", RACKET_SDK "/share/racket/collects"};
  racket_boot_arguments_t boot = {0};
  boot.boot1_path = RACKET_SDK "/lib/racket/petite.boot";
  boot.boot2_path = RACKET_SDK "/lib/racket/scheme.boot";
  boot.boot3_path = RACKET_SDK "/lib/racket/racket.boot";
  boot.exec_file = RACKET_SDK "/bin/racket";
  boot.collects_dir = RACKET_SDK "/share/racket/collects";
  boot.config_dir = RACKET_CONFIG_DIR;
  boot.argc = sizeof(arguments)/sizeof(arguments[0]);
  boot.argv = arguments;
  boot.gracket_guid_or_x11_args = "";
  racket_boot(&boot);
#endif
  ptr module = Scons(Sstring_to_symbol("file"), Scons(Sstring(RACKET_MODULE), Snil));
  ptr values = racket_dynamic_require(module, Sstring_to_symbol("answer"));
  procedure = Scar(values);
  Slock_object(procedure);
  return 0;
}
uint32_t ANSWER(uint32_t value) {
  ptr values = racket_apply(procedure, Scons(Sfixnum((iptr)value), Snil));
  return (uint32_t)Sinteger_value(Scar(values));
}
