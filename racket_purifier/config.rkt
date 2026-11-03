#lang racket/base
(require racket/file racket/path racket/list)
(define args (current-command-line-arguments))
(define sdk-config (vector-ref args 0))
(define env (path->complete-path (vector-ref args 1)))
(define dest (path->complete-path (vector-ref args 2)))
(define addon (build-path env "addon" (version)))
(define original (call-with-input-file sdk-config read))
(define sdk-share (hash-ref original 'share-dir))
(define result
  (hash-set*
   original
   'share-dir (path->string (build-path addon "share"))
   'links-file (path->string (build-path addon "links.rktd"))
   'links-search-files (list (path->string (build-path addon "links.rktd")) (path->string (build-path sdk-share "links.rktd")))
   'pkgs-search-dirs (list (path->string (build-path addon "pkgs")) (hash-ref original 'pkgs-dir))
   'lib-search-dirs (cons (path->string (build-path addon "lib")) (hash-ref original 'lib-search-dirs))
   'catalogs '()))
(make-directory* dest)
(call-with-output-file (build-path dest "config.rktd") #:exists 'replace
  (lambda (out)
    (display "#hash(" out)
    (for ([key (in-list (sort (hash-keys result) symbol<?))])
      (display "(" out) (write key out) (display " . " out) (write (hash-ref result key) out) (display ")" out)
      (newline out))
    (display ")\n" out)))
