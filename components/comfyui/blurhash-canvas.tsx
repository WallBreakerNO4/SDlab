"use client"

import { useEffect, useRef } from "react"
import { decodeBlurHash } from "fast-blurhash"

type BlurhashCanvasProps = {
  blurhash: string
  width?: number
  height?: number
  className?: string
}

export function BlurhashCanvas({ blurhash, width = 32, height = 32, className }: BlurhashCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    try {
      const pixels = decodeBlurHash(blurhash, width, height)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const imageData = new ImageData(pixels as any, width, height)
      ctx.putImageData(imageData, 0, 0)
    } catch (error) {
      console.error("Failed to decode blurhash:", error)
    }
  }, [blurhash, width, height])

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      className={className}
      aria-hidden="true"
      data-testid="blurhash-canvas"
    />
  )
}
