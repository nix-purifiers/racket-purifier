import java.lang.foreign.*;
import static java.lang.foreign.ValueLayout.JAVA_INT;
class NativeAnswer {
  public static void main(String[] args) throws Throwable {
    System.loadLibrary("first"); System.loadLibrary("second");
    var lookup = SymbolLookup.loaderLookup();
    var linker = Linker.nativeLinker();
    var init = linker.downcallHandle(lookup.find("first_init").orElseThrow(), FunctionDescriptor.of(JAVA_INT));
    var bind = linker.downcallHandle(lookup.find("second_bind").orElseThrow(), FunctionDescriptor.of(JAVA_INT));
    if ((int)init.invokeExact()!=0 || (int)bind.invokeExact()!=0) throw new AssertionError();
    var first = linker.downcallHandle(lookup.find("first_answer").orElseThrow(), FunctionDescriptor.of(JAVA_INT,JAVA_INT));
    var second = linker.downcallHandle(lookup.find("second_answer").orElseThrow(), FunctionDescriptor.of(JAVA_INT,JAVA_INT));
    int expected = Integer.parseInt(args[0]);
    for (int i=0;i<100;i++) {
      if ((int)first.invokeExact(i)!=i+expected || (int)second.invokeExact(i)!=i+expected+1) throw new AssertionError();
    }
    if ((int)first.invokeExact(-1)!=expected-1 || (int)second.invokeExact(-1)!=expected) throw new AssertionError();
    System.out.println("Actual shared-CS Racket Java FFM200/GC/overflow PASS");
  }
}
