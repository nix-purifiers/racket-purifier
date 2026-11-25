#lang racket/base
(require threading)
(provide answer)
(define (answer) (~> 40 add1 add1))
(module+ test
  (require rackunit)
  (check-equal? (answer) 42))
(module+ main (displayln (answer)))
