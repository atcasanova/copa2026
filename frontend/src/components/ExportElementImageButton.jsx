import React, { useState } from 'react'
import { Button } from '@mui/material'
import {
  Download as DownloadIcon,
  Share as ShareIcon
} from '@mui/icons-material'

const copyComputedStyles = (source, target) => {
  const computed = window.getComputedStyle(source)
  for (let i = 0; i < computed.length; i++) {
    const key = computed[i]
    target.style.setProperty(
      key,
      computed.getPropertyValue(key),
      computed.getPropertyPriority(key)
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

// Emoji matching and replacement
const emojiRegex = /(?:[\u{1F300}-\u{1F5FF}]|[\u{1F600}-\u{1F64F}]|[\u{1F680}-\u{1F6FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]|[\u{1F900}-\u{1F9FF}]|[\u{1F7E0}-\u{1F7F0}]|[\u{1F1E6}-\u{1F1FF}]{2})/gu

const getEmojiHex = (emoji) => Array.from(emoji).map(c => c.codePointAt(0).toString(16)).join("-")

const replaceEmojisInTextNode = (textNode) => {
  const text = textNode.nodeValue
  if (!text) return
  
  emojiRegex.lastIndex = 0
  if (!emojiRegex.test(text)) return
  
  const parent = textNode.parentNode
  if (!parent) return
  
  const doc = parent.ownerDocument || document
  const fragment = doc.createDocumentFragment()
  
  let lastIndex = 0
  let match
  
  const matches = []
  emojiRegex.lastIndex = 0
  while ((match = emojiRegex.exec(text)) !== null) {
    matches.push(match)
  }
  
  if (matches.length === 0) return
  
  matches.forEach((match) => {
    const emoji = match[0]
    const index = match.index
    
    if (index > lastIndex) {
      fragment.appendChild(doc.createTextNode(text.substring(lastIndex, index)))
    }
    
    const hex = getEmojiHex(emoji)
    const img = doc.createElement('img')
    img.src = `https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/svg/${hex}.svg`
    img.style.width = '1.2em'
    img.style.height = '1.2em'
    img.style.display = 'inline-block'
    img.style.verticalAlign = 'middle'
    img.style.margin = '0 0.1em'
    img.setAttribute('alt', emoji)
    fragment.appendChild(img)
    
    lastIndex = index + emoji.length
  })
  
  if (lastIndex < text.length) {
    fragment.appendChild(doc.createTextNode(text.substring(lastIndex)))
  }
  
  parent.replaceChild(fragment, textNode)
}

const walkAndReplaceEmojis = (node) => {
  if (node.nodeName === 'SCRIPT' || node.nodeName === 'STYLE') return
  
  if (node.nodeType === 3) { // Node.TEXT_NODE
    replaceEmojisInTextNode(node)
    return
  }
  
  const children = Array.from(node.childNodes)
  children.forEach(walkAndReplaceEmojis)
}

// Inlines local/remote images (CORS-proxied if remote) into Base64 data URLs
const inlineImagesForExport = async (clone) => {
  const imgs = Array.from(clone.querySelectorAll('img'))
  
  await Promise.all(imgs.map(async (img) => {
    let src = img.getAttribute('src')
    if (!src || src.startsWith('data:')) return

    try {
      const isRemote = src.startsWith('http://') || src.startsWith('https://')
      const isSameOrigin = src.startsWith(window.location.origin)
      
      let fetchUrl = src
      if (isRemote && !isSameOrigin) {
        fetchUrl = `/api/proxy-image?url=${encodeURIComponent(src)}`
      } else {
        fetchUrl = new URL(src, window.location.href).href
      }
      
      const response = await fetch(fetchUrl)
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
      const blob = await response.blob()
      
      const dataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onloadend = () => resolve(reader.result)
        reader.onerror = reject
        reader.readAsDataURL(blob)
      })
      
      img.src = dataUrl
      img.setAttribute('src', dataUrl)
    } catch (err) {
      console.error('Failed to inline image:', src, err)
      // Remove broken/CORS-blocked img to let initials fallback if inside MUI Avatar
      try {
        img.remove()
      } catch (e) {
        img.style.display = 'none'
      }
    }
  }))
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

  // 1. Convert emojis to Twemoji <img> elements
  walkAndReplaceEmojis(clone)

  // 2. Load and inline all images (including Twemoji SVGs) into base64 Data URLs
  await inlineImagesForExport(clone)

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
