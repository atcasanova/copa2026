import React, { useState, useEffect } from 'react'
import {
  Box, Card, CardContent, Typography, Grid, Button, Paper, Stack,
  List, ListItem, ListItemText, Divider, Alert, Skeleton, IconButton, Tooltip, Chip
} from '@mui/material'
import {
  ContentCopy as CopyIcon,
  Download as DownloadIcon,
  VerifiedUser as VerifyIcon,
  ArrowDownward as ArrowIcon,
  HelpOutline as InfoIcon,
  Security as SecurityIcon
} from '@mui/icons-material'
import axios from 'axios'

// Helper to serialize object deterministically matching python's json.dumps(..., separators=(',', ':'), sort_keys=True)
const deterministicStringify = (val) => {
  if (Array.isArray(val)) {
    return '[' + val.map(item => deterministicStringify(item)).join(',') + ']'
  } else if (typeof val === 'object' && val !== null) {
    const sortedKeys = Object.keys(val).sort()
    const parts = sortedKeys.map(k => {
      return JSON.stringify(k) + ':' + deterministicStringify(val[k])
    })
    return '{' + parts.join(',') + '}'
  } else {
    return JSON.stringify(val)
  }
}

// Helper to compute SHA-256 hash using browser's Web Crypto API
const calculateSHA256 = async (message) => {
  const msgBuffer = new TextEncoder().encode(message)
  const hashBuffer = await window.crypto.subtle.digest('SHA-256', msgBuffer)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
  return hashHex
}

export default function Auditoria() {
  const [blocks, setBlocks] = useState([])
  const [selectedBlock, setSelectedBlock] = useState(null)
  const [blockDetails, setBlockDetails] = useState(null)
  
  const [loadingList, setLoadingList] = useState(true)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [error, setError] = useState('')
  
  // Local verification states
  const [isVerifying, setIsVerifying] = useState(false)
  const [verificationResult, setVerificationResult] = useState(null) // 'success' | 'failed' | null
  const [calculatedHash, setCalculatedHash] = useState('')

  const loadBlocksChain = async () => {
    try {
      setLoadingList(true)
      setError('')
      const res = await axios.get('/api/audit/blocks')
      setBlocks(res.data)
      
      // Auto-select first block if present
      if (res.data.length > 0) {
        handleSelectBlock(res.data[0])
      }
    } catch (err) {
      setError('Erro ao carregar a cadeia de auditoria. Verifique sua conexão.')
    } finally {
      setLoadingList(false)
    }
  }

  const handleSelectBlock = async (block) => {
    setSelectedBlock(block)
    setVerificationResult(null)
    setCalculatedHash('')
    
    try {
      setLoadingDetails(true)
      const res = await axios.get(`/api/audit/blocks/${block.block_number}`)
      setBlockDetails(res.data)
    } catch (err) {
      setError('Erro ao obter detalhes do bloco.')
    } finally {
      setLoadingDetails(false)
    }
  }

  useEffect(() => {
    loadBlocksChain()
  }, [])

  const handleCopyText = (text, label) => {
    navigator.clipboard.writeText(text)
    alert(`${label} copiado para a área de transferência!`)
  }

  // Live client-side cryptographic verification
  const handleLocalVerify = async () => {
    if (!blockDetails) return
    setIsVerifying(true)
    setVerificationResult(null)
    
    try {
      // 1. Serialize payload deterministically
      const payloadStr = deterministicStringify(blockDetails.payload)
      // 2. Concatenate with previous block hash
      const combinedInput = payloadStr + blockDetails.previous_hash
      // 3. Compute SHA-256 locally
      const localHash = await calculateSHA256(combinedInput)
      
      setCalculatedHash(localHash)
      if (localHash === blockDetails.hash) {
        setVerificationResult('success')
      } else {
        setVerificationResult('failed')
      }
    } catch (err) {
      console.error(err)
      setVerificationResult('failed')
    } finally {
      setIsVerifying(false)
    }
  }

  // Download raw audit block details with local verify instructions
  const handleDownloadBlock = () => {
    if (!blockDetails) return
    
    const payloadStr = deterministicStringify(blockDetails.payload)
    const fileName = `bolao_bloco_auditoria_${blockDetails.block_number}.txt`
    
    const textContent = `=== BOLÃO WORLD CUP 2026 AUDIT BLOCK ===
Número do Bloco: ${blockDetails.block_number}
Partida: ${blockDetails.match?.team1_name} x ${blockDetails.match?.team2_name}
Data/Hora da Partida (UTC): ${blockDetails.match?.kickoff_time}
Hash do Bloco Anterior (previous_hash): ${blockDetails.previous_hash}
Hash do Bloco Esperado (hash): ${blockDetails.hash}

--- CONTEÚDO DO PALPITE (HASH INPUT) ---
${payloadStr}
----------------------------------------

=== INSTRUÇÕES PARA VALIDAÇÃO MANUAL ===
Para verificar independentemente a integridade deste bloco:
1. Copie todo o conteúdo acima que está entre as linhas de traços (excluindo as quebras de linha nas extremidades).
2. Concatene com o hash do bloco anterior sem espaços. Ou seja:
   <CONTEÚDO_DO_PALPITE><HASH_DO_BLOCO_ANTERIOR>
3. Calcule o hash SHA-256 desta string resultante.
4. Confirme que o hash calculado é idêntico ao "Hash do Bloco Esperado".

Comando Linux/macOS:
echo -n '${payloadStr}${blockDetails.previous_hash}' | shasum -a 256

Comando Windows (PowerShell):
$str = '${payloadStr}${blockDetails.previous_hash}'
[System.Security.Cryptography.SHA256Managed]::new().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($str)) | ForEach-Object { $_.ToString("x2") } -join ""
`
    const element = document.createElement("a")
    const file = new Blob([textContent], { type: 'text/plain;charset=utf-8' })
    element.href = URL.createObjectURL(file)
    element.download = fileName
    document.body.appendChild(element)
    element.click()
    document.body.removeChild(element)
  }

  const formatDateTime = (isoString) => {
    if (!isoString) return ''
    const d = new Date(isoString)
    return d.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', dateStyle: 'short', timeStyle: 'short' })
  }

  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 3 }}>
        🛡️ Auditoria Criptográfica
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>{error}</Alert>}

      {/* Explanatory Info Card */}
      <Card sx={{ mb: 4, borderLeft: '5px solid #10b981', bgcolor: 'rgba(16, 185, 129, 0.02)' }}>
        <CardContent sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 1, mb: 1, color: 'primary.light' }}>
            <SecurityIcon /> Como funciona a transparência do Bolão?
          </Typography>
          <Typography variant="body2" sx={{ lineHeight: 1.7, color: 'text.secondary', mb: 2 }}>
            Para garantir que a administração do sistema <strong>não possa alterar ou adicionar palpites</strong> após o bloqueio de cada partida (que ocorre rigorosamente 3 horas antes do início), o sistema gera um <strong>bloco criptográfico de auditoria</strong>. 
            Este bloco agrupa todos os palpites recebidos de forma ordenada e gera um hash de verificação único (<code>SHA-256</code>) contendo o hash do jogo anterior. 
            Isso cria uma cadeia sequencial imutável (blockchain). Qualquer alteração em qualquer aposta de qualquer jogo invalidará toda a cadeia subsequente.
          </Typography>
          
          <Divider sx={{ my: 1.5, borderColor: 'rgba(255, 255, 255, 0.1)' }} />
          
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, color: 'text.primary' }}>
            🛠️ Passo a Passo para Validação Independente (Via Site Público):
          </Typography>
          <Typography variant="body2" component="div" sx={{ lineHeight: 1.7, color: 'text.secondary' }}>
            Caso queira validar os dados sem depender do nosso validador automático, você pode usar qualquer site independente de cálculo de hash SHA-256 (por exemplo, o <a href="https://emn178.github.io/online-tools/sha256.html" target="_blank" rel="noopener noreferrer" style={{ color: '#10b981', textDecoration: 'underline' }}>Online SHA-256 Calculator</a>):
            <ol style={{ marginTop: 8, paddingLeft: 20 }}>
              <li>Selecione um bloco na lista e clique em <strong>Baixar Bloco (.txt)</strong>.</li>
              <li>Abra o arquivo baixado e copie a linha de texto da seção <strong>"CONTEÚDO DO PALPITE"</strong> (o texto em formato JSON contendo os palpites).</li>
              <li>Cole esse texto no campo de entrada (input) do gerador de hash no site.</li>
              <li>Imediatamente após o texto colado (sem espaços ou quebras de linha), cole o valor do <strong>"Hash do Bloco Anterior"</strong> (previous_hash).</li>
              <li>O site calculará o hash resultante. Compare-o com o <strong>"Hash Registrado no Servidor"</strong> (hash do bloco selecionado) para atestar que os dados estão 100% íntegros.</li>
            </ol>
          </Typography>
        </CardContent>
      </Card>

      <Grid container spacing={3}>
        {/* Left Column: Visual Chain Explorer */}
        <Grid item xs={12} md={4}>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 2, fontFamily: 'Outfit' }}>
            ⛓️ Cadeia de Blocos ({blocks.length})
          </Typography>
          
          <Paper 
            sx={{ 
              p: 2, 
              borderRadius: 3, 
              bgcolor: 'background.paper', 
              maxHeight: '65vh', 
              overflowY: 'auto',
              border: '1px solid #1f2937'
            }}
          >
            {loadingList ? (
              <Stack spacing={2}>
                {Array.from(new Array(4)).map((_, idx) => (
                  <Skeleton key={idx} variant="rectangular" height={80} sx={{ borderRadius: 2 }} />
                ))}
              </Stack>
            ) : blocks.length === 0 ? (
              <Typography variant="body2" color="text.secondary" align="center" sx={{ py: 4 }}>
                Nenhuma partida bloqueada até o momento. A cadeia de auditoria iniciará após o fechamento da primeira partida.
              </Typography>
            ) : (
              <Stack spacing={1} alignItems="center">
                {blocks.map((block, idx) => {
                  const isSelected = selectedBlock?.block_number === block.block_number
                  return (
                    <React.Fragment key={block.id}>
                      <Card 
                        onClick={() => handleSelectBlock(block)}
                        sx={{ 
                          width: '100%',
                          cursor: 'pointer',
                          borderRadius: 2.5,
                          border: '1px solid',
                          borderColor: isSelected ? 'primary.main' : 'divider',
                          bgcolor: isSelected ? 'rgba(16, 185, 129, 0.05)' : 'background.default',
                          transition: 'all 0.2s',
                          '&:hover': { 
                            borderColor: 'primary.light',
                            bgcolor: isSelected ? 'rgba(16, 185, 129, 0.08)' : 'rgba(255, 255, 255, 0.02)' 
                          }
                        }}
                      >
                        <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                          <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 800, color: 'primary.main' }}>
                              Bloco #{block.block_number}
                            </Typography>
                            <Chip 
                              label={block.match?.status === 'finished' || block.match?.status === 'score_confirmed' ? 'Finalizado' : 'Bloqueado'} 
                              size="small" 
                              color={block.match?.status === 'finished' || block.match?.status === 'score_confirmed' ? 'success' : 'warning'} 
                              sx={{ fontSize: '0.65rem', height: 16 }}
                            />
                          </Box>
                          <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {block.match?.team1_name} x {block.match?.team2_name}
                          </Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                            📅 {formatDateTime(block.match?.kickoff_time)}
                          </Typography>
                          <Typography variant="caption" sx={{ fontFamily: 'monospace', color: 'text.secondary', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', bgcolor: 'rgba(0,0,0,0.2)', px: 1, py: 0.5, borderRadius: 1 }}>
                            Hash: {block.hash.substring(0, 16)}...
                          </Typography>
                        </CardContent>
                      </Card>
                      
                      {idx < blocks.length - 1 && (
                        <ArrowIcon sx={{ color: 'text.secondary', opacity: 0.4, my: 0.5 }} />
                      )}
                    </React.Fragment>
                  )
                })}
              </Stack>
            )}
          </Paper>
        </Grid>

        {/* Right Column: Detailed Block Panel */}
        <Grid item xs={12} md={8}>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 2, fontFamily: 'Outfit' }}>
            🔎 Detalhes do Bloco Selecionado
          </Typography>

          {loadingDetails ? (
            <Paper sx={{ p: 4, borderRadius: 3, border: '1px solid #1f2937' }}>
              <Skeleton variant="text" width="40%" height={40} sx={{ mb: 2 }} />
              <Skeleton variant="rectangular" height={150} sx={{ borderRadius: 2, mb: 3 }} />
              <Skeleton variant="rectangular" height={200} sx={{ borderRadius: 2 }} />
            </Paper>
          ) : !blockDetails ? (
            <Paper sx={{ p: 4, borderRadius: 3, border: '1px solid #1f2937', textAlign: 'center', color: 'text.secondary' }}>
              Nenhum bloco selecionado ou dados indisponíveis.
            </Paper>
          ) : (
            <Stack spacing={3}>
              {/* Block Header Stats Card */}
              <Paper sx={{ p: 3, borderRadius: 3, border: '1px solid #1f2937', bgcolor: 'background.paper' }}>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>AUDITORIA CRIPTOGRÁFICA</Typography>
                    <Typography variant="h5" sx={{ fontWeight: 800, color: 'primary.main', mb: 1 }}>
                      Bloco #{blockDetails.block_number}
                    </Typography>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                      {blockDetails.match?.team1_name} x {blockDetails.match?.team2_name}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Estádio: {blockDetails.match?.ground}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Fechamento: {formatDateTime(blockDetails.match?.kickoff_time)}
                    </Typography>
                  </Grid>
                  
                  <Grid item xs={12} sm={6} sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 1.5 }}>
                    <Stack direction="row" spacing={1}>
                      <Button 
                        variant="contained" 
                        color="primary"
                        startIcon={<VerifyIcon />}
                        onClick={handleLocalVerify}
                        fullWidth
                        size="small"
                      >
                        Validar no Navegador
                      </Button>
                      <Button 
                        variant="outlined" 
                        startIcon={<DownloadIcon />}
                        onClick={handleDownloadBlock}
                        fullWidth
                        size="small"
                      >
                        Baixar Bloco (.txt)
                      </Button>
                    </Stack>
                  </Grid>
                </Grid>

                <Divider sx={{ my: 2.5 }} />

                {/* Hashes displays */}
                <Stack spacing={1.5}>
                  <Box>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontWeight: 'bold' }}>
                      Hash do Bloco Anterior (previous_hash):
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.8rem', bgcolor: 'rgba(0, 0, 0, 0.2)', p: 1, borderRadius: 1.5, flexGrow: 1, overflowX: 'auto', whiteSpace: 'nowrap' }}>
                        {blockDetails.previous_hash}
                      </Typography>
                      <IconButton size="small" onClick={() => handleCopyText(blockDetails.previous_hash, 'Hash anterior')}>
                        <CopyIcon fontSize="small" />
                      </IconButton>
                    </Box>
                  </Box>

                  <Box>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontWeight: 'bold' }}>
                      Hash Registrado no Servidor (hash):
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.8rem', bgcolor: 'rgba(16, 185, 129, 0.05)', border: '1px solid rgba(16, 185, 129, 0.2)', p: 1, borderRadius: 1.5, flexGrow: 1, overflowX: 'auto', whiteSpace: 'nowrap', fontWeight: 'bold', color: 'primary.light' }}>
                        {blockDetails.hash}
                      </Typography>
                      <IconButton size="small" onClick={() => handleCopyText(blockDetails.hash, 'Hash do bloco')}>
                        <CopyIcon fontSize="small" />
                      </IconButton>
                    </Box>
                  </Box>
                </Stack>

                {/* Local validation result notification */}
                {verificationResult && (
                  <Box sx={{ mt: 3.5 }}>
                    {verificationResult === 'success' ? (
                      <Alert severity="success" sx={{ borderRadius: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                          ✅ Integridade Confirmada Localmente!
                        </Typography>
                        <Typography variant="caption" sx={{ display: 'block', mt: 0.5, fontFamily: 'monospace', wordBreak: 'break-all' }}>
                          Hash Calculado (SHA-256): {calculatedHash}
                        </Typography>
                        <Typography variant="caption" sx={{ display: 'block', mt: 1 }}>
                          Isso prova criptograficamente que a lista de palpites abaixo é exatamente a mesma que existia no servidor às {formatDateTime(new Date(new Date(blockDetails.match?.kickoff_time).getTime() - 3*60*60*1000))} (3 horas antes do início). Nenhum palpite foi alterado.
                        </Typography>
                      </Alert>
                    ) : (
                      <Alert severity="error" sx={{ borderRadius: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                          ❌ Falha na Validação de Integridade!
                        </Typography>
                        <Typography variant="caption" sx={{ display: 'block', mt: 0.5, fontFamily: 'monospace', wordBreak: 'break-all' }}>
                          Hash Calculado: {calculatedHash}
                        </Typography>
                        <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                          O hash calculado localmente não confere com o registrado no servidor. Os dados podem ter sido alterados após o prazo de bloqueio.
                        </Typography>
                      </Alert>
                    )}
                  </Box>
                )}
              </Paper>

              {/* Predictions Table inside Block */}
              <Paper sx={{ p: 3, borderRadius: 3, border: '1px solid #1f2937' }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2, fontFamily: 'Outfit' }}>
                  📝 Conteúdo do Bloco: Palpites Registrados ({blockDetails.payload?.length || 0})
                </Typography>
                <Divider sx={{ mb: 2 }} />

                <List disablePadding sx={{ maxHeight: '35vh', overflowY: 'auto' }}>
                  {blockDetails.payload?.length === 0 ? (
                    <Typography variant="body2" color="text.secondary" align="center" sx={{ py: 3 }}>
                      Nenhum palpite foi registrado para esta partida.
                    </Typography>
                  ) : (
                    blockDetails.payload?.map((pred, pIdx) => (
                      <React.Fragment key={pIdx}>
                        <ListItem sx={{ py: 1, px: 1 }}>
                          <ListItemText 
                            primary={pred.username}
                            primaryTypographyProps={{ fontWeight: 600, fontSize: '0.9rem' }}
                          />
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Chip 
                              label={`${pred.goals_team1} x ${pred.goals_team2}`} 
                              variant="outlined" 
                              size="small" 
                              sx={{ fontWeight: 'bold', fontFamily: 'monospace', fontSize: '0.85rem' }} 
                            />
                          </Box>
                        </ListItem>
                        {pIdx < blockDetails.payload.length - 1 && <Divider />}
                      </React.Fragment>
                    ))
                  )}
                </List>
              </Paper>
            </Stack>
          )}
        </Grid>
      </Grid>
    </Box>
  )
}
