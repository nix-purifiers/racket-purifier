#lang racket/base
(require threading)
(provide answer)
(displayln "Native Racket module initialization output")
(define (answer value)
  (define bytes (make-bytes 64 41))
  (define result (~> value (+ (bytes-ref bytes 0))))
  (collect-garbage)
  (bitwise-and #xffffffff result))
