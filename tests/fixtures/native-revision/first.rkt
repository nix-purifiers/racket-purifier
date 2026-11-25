#lang racket/base
(require threading)
(provide answer)
(define (answer value)
  (define bytes (make-bytes 64 42))
  (define result (~> value (+ (bytes-ref bytes 0))))
  (collect-garbage)
  (bitwise-and #xffffffff result))
