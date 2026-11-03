#lang racket/base
(require pkg/lib json setup/getinfo racket/path)
(define args (current-command-line-arguments))
(define mode (vector-ref args 0))
(define manifest (call-with-input-file (vector-ref args 1) read-json))
(define directory (string->path (vector-ref args 2)))
(define info (get-info/full directory))
(define project (hash-ref manifest 'project))
(unless (equal? (info 'version (lambda () "0.0")) (hash-ref project 'version))
  (error 'racket-purifier "Project version differs from native capture; regenerate the lock"))
(cond
  [(equal? mode "link")
   (parameterize ([current-pkg-scope 'user] [current-pkg-catalogs '()])
     (with-pkg-lock
       (pkg-install (list (pkg-desc (path->string directory) 'link (hash-ref project 'name) #f #f))
                    #:dep-behavior 'fail #:quiet? #t)))]
  [(equal? mode "release")
   (pkg-create 'zip directory #:pkg-name (hash-ref project 'name) #:mode 'source
               #:dest (vector-ref args 3))]
  [else (error 'racket-purifier "Unknown project operation")])
