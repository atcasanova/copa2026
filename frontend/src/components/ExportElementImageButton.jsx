import React, { useState } from 'react'
import { Button } from '@mui/material'
import {
  Download as DownloadIcon,
  Share as ShareIcon
} from '@mui/icons-material'

const copyComputedStyles = (source, target) => {
  const computed = window.getComputedStyle(source)
  for (const property of computed) {
    target.style.setProperty(
      property,
      computed.getPropertyValue(property),
      computed.getPropertyPriority(property)
    )
  }

  Array.from(source.children).forEach((sourceChild, index) => {
    const targetChild = target.children[index]
    if (targetChild) copyComputedStyles(sourceChild, targetChild)
  })
}

const blobToDataUrl = (blob) => new Promise((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => resolve(reader.result)
  reader.onerror = reject
  reader.readAsDataURL(blob)
})

const prepareImagesForExport = (clone) => {
  clone.querySelectorAll('img').forEach((img) => {
    try {
      img.remove()
    } catch (err) {
      img.style.display = 'none'
    }
  })
}

const canvasToBlob = (canvas) => new Promise((resolve) => {
  canvas.toBlob(resolve, 'image/png', 1)
})

async function renderElementToPngBlob(element) {
  const rect = element.getBoundingClientRect()
  const width = Math.ceil(rect.width)
  const height = Math.ceil(rect.height)
  const clone = element.cloneNode(true)
  copyComputedStyles(element, clone)

  clone.style.width = `${width}px`
  clone.style.height = `${height}px`
  clone.style.margin = '0'
  clone.style.boxSizing = 'border-box'
  clone.setAttribute('xmlns', 'http://www.w3.org/1999/xhtml')
  prepareImagesForExport(clone)

  const serialized = new XMLSerializer().serializeToString(clone)
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
      <foreignObject width="100%" height="100%">
        ${serialized}
      </foreignObject>
    </svg>
  `
  const svgBlob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' })
  const dataUrl = await blobToDataUrl(svgBlob)

  const image = new Image()
  image.decoding = 'async'
  const imageLoaded = new Promise((resolve, reject) => {
    image.onload = resolve
    image.onerror = reject
  })
  image.src = dataUrl
  await imageLoaded

  const scale = Math.min(2, window.devicePixelRatio || 1)
  const canvas = document.createElement('canvas')
  canvas.width = width * scale
  canvas.height = height * scale
  const ctx = canvas.getContext('2d')
  ctx.setTransform(scale, 0, 0, scale, 0, 0)
  ctx.drawImage(image, 0, 0, width, height)

  const blob = await canvasToBlob(canvas)
  if (!blob) throw new Error('Não foi possível gerar a imagem.')
  return blob
}

export default function ExportElementImageButton({
  targetRef,
  fileName = 'ranking.png',
  label = 'Exportar PNG',
  shareTitle = 'Ranking do Bolão',
  size = 'small',
  variant = 'outlined',
  color = 'primary',
  fullWidth = false,
}) {
  const [exporting, setExporting] = useState(false)
  const canShareFiles = Boolean(navigator.canShare && navigator.share)

  const handleExport = async () => {
    if (!targetRef?.current || exporting) return
    setExporting(true)
    try {
      const blob = await renderElementToPngBlob(targetRef.current)
      const file = new File([blob], fileName, { type: 'image/png' })

      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({
          title: shareTitle,
          files: [file],
        })
      } else {
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = fileName
        document.body.appendChild(link)
        link.click()
        link.remove()
        URL.revokeObjectURL(url)
      }
    } catch (err) {
      alert(err.message || 'Erro ao exportar a imagem.')
    } finally {
      setExporting(false)
    }
  }

  return (
    <Button
      variant={variant}
      color={color}
      size={size}
      fullWidth={fullWidth}
      startIcon={canShareFiles ? <ShareIcon /> : <DownloadIcon />}
      onClick={handleExport}
      disabled={exporting}
    >
      {exporting ? 'Gerando...' : label}
    </Button>
  )
}
