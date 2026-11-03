#lang racket/base
(require pkg/lib pkg/name pkg/private/repo-path
         setup/getinfo net/url json racket/list racket/path racket/string racket/match)

(define root-name (vector-ref (current-command-line-arguments) 0))
(define root-path (vector-ref (current-command-line-arguments) 1))
(define root-info (get-info/full (string->path root-path)))
(define sdk
  (for/list ([name (in-list (installed-pkg-names #:scope 'installation))])
    (define info (hash-ref (installed-pkg-table #:scope 'installation) name))
    (hasheq 'name name 'checksum (pkg-info-checksum info))))
(define table (installed-pkg-table #:scope 'user))
(define records
  (for/list ([name (in-list (sort (hash-keys table) string<?))]
             #:unless (equal? name root-name))
    (define info (hash-ref table name))
    (define source
      (match (pkg-info-orig-pkg info)
        [`(catalog ,_ . ,_)
         (define details (get-pkg-details-from-catalogs name))
         (unless (equal? (pkg-info-checksum info) (hash-ref details 'checksum))
           (error 'capture "catalog changed during resolution for ~a" name))
         (hash-ref details 'source)]
        [`(url ,source) source]
        [`(git ,source) source]
        [_ (error 'capture "Unsupported package origin for ~a" name)]))
    (define-values (source-name source-type) (package-source->name+type source #f))
    (define record
      (hasheq 'name name 'checksum (pkg-info-checksum info)
              'source source 'type (symbol->string source-type)
              'directory (path->string (pkg-directory name))))
    (if (memq source-type '(git git-url github))
        (let-values ([(transport host port repo branch path)
                      (split-git-or-hub-url (string->url source) #:type source-type)])
          (hash-set record 'git
                    (hasheq 'url (real-git-url (string->url source) host port repo #:type source-type)
                            'subpath (string-join path "/"))))
        record)))
(write-json
 (hasheq 'project (hasheq 'name root-name 'version (root-info 'version (lambda () "0.0")))
         'sdkPackages sdk 'packages records 'vm (symbol->string (system-type 'vm))))
(newline)
