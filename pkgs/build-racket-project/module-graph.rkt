#lang racket/base
(require json racket/path racket/list syntax/modcode compiler/cm)
(define args (current-command-line-arguments))
(define metadata-output (current-output-port))
;; Ordinary module initialization may print. Preserve those diagnostics without
;; allowing application output to corrupt this inspector's JSON channel.
(current-output-port (current-error-port))
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
(define compiled (make-hash))
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
       (define-values (selected kind) (get-module-path source))
       (when (eq? kind 'zo)
         (define dep (path-replace-extension selected #".dep"))
         (unless (file-exists? dep)
           (error 'racket-native "Missing native compiled-module dependency record: ~a" dep))
         (define metadata (call-with-input-file dep read))
         (define original-sha1 (get-file-sha1 source))
         (unless (and (list? metadata) (>= (length metadata) 3)
                      (equal? (car metadata) (version))
                      (pair? (caddr metadata))
                      (equal? (car (caddr metadata)) original-sha1))
           (error 'racket-native "Native compiled-module source digest mismatch: ~a" source))
         (hash-set! compiled (path->string (simplify-path source))
                    (hash 'source (path->string (simplify-path source))
                          'path (path->string selected) 'dependencyRecord (path->string dep)
                          'sourceSha1 original-sha1)))
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
                  'compiled (for/list ([name (in-list (sort (hash-keys compiled) string<?))])
                              (hash-ref compiled name))
                  'compiledPaths (map path->string (use-compiled-file-paths))) metadata-output)
(newline metadata-output)
