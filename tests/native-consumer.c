#include <assert.h>
#include "native-answer.h"
int main(void) {
  assert(first_init() == 0);
  assert(second_bind() == 0);
  for (uint32_t value=0; value<100; value++) {
    assert(first_answer(value) == value+EXPECTED);
    assert(second_answer(value) == value+EXPECTED+1);
  }
  assert(first_answer(UINT32_MAX) == EXPECTED-1);
  assert(second_answer(UINT32_MAX) == EXPECTED);
  return 0;
}
