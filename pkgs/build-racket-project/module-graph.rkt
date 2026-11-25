#lang racket/base
(require json racket/path racket/list)
(define args (current-command-line-arguments))
(define root (path->complete-path (vector-ref args 0)))
(define bindings (call-with-input-file (vector-ref args 1) read-json))
(dynamic-require root #f)
(define binding-info
  (for/list ([name (in-list bindings)])
    (define value (dynamic-require root (string->symbol name)))
    (unless (procedure? value)
      (error 'racket-native "Selected native Racket binding is not a procedure: ~a" name))
    (hash 'name name 'arity (format "~s" (procedure-arity value)))))
(define seen (make-hash))
(define files (make-hash))
(define builtins (make-hash))
(define (walk module)
  (define resolved
    (if (resolved-module-path? module) module
        (module-path-index-resolve (module-path-index-join module #f))))
  (define name (resolved-module-path-name resolved))
  (unless (hash-ref seen name #f)
    (hash-set! seen name #t)
    (define source (if (and (pair? name) (path? (car name))) (car name) name))
    (cond
      [(path? source)
       (hash-set! files (path->string (simplify-path source)) #t)
       (for* ([imports (in-list (module->imports resolved))]
              [index (in-list (cdr imports))])
         ;; Native import indexes retain a relative self index. Rebase that
         ;; index onto the actual declaring module, not the inspector's cwd.
         (define (rebase index)
           (define-values (path base) (module-path-index-split index))
           (if path
               (module-path-index-join path (if base (rebase base) resolved))
               resolved))
         (walk (module-path-index-resolve (rebase index))))]
      [(symbol? source) (hash-set! builtins (symbol->string source) #t)]
      [else (error 'racket-native "Unknown native module origin: ~s" name)])))
(walk root)
(write-json (hash 'bindings binding-info
                  'files (sort (hash-keys files) string<?)
                  'builtins (sort (hash-keys builtins) string<?)
                  'compiledPaths (map path->string (use-compiled-file-paths))))
(newline)
