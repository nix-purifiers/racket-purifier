#lang racket/base
(require pkg/lib json racket/list)
(define data (call-with-input-file (vector-ref (current-command-line-arguments) 0) read-json))
(define expected (make-immutable-hash (for/list ([item (in-list (hash-ref data 'packages))])
                                      (cons (hash-ref item 'name) (hash-ref item 'checksum)))))
(define actual (for/hash ([(name info) (in-hash (installed-pkg-table #:scope 'user))])
                 (values name (pkg-info-checksum info))))
(unless (equal? actual expected)
  (error 'racket-purifier "Installed package names/checksums differ from the native capture"))
