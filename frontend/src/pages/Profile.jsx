import React, { useState, useEffect } from 'react'
import { Box, Card, CardContent, Grid, TextField, Button, Typography, FormControlLabel, Checkbox, Stack, Avatar, Alert, Snackbar, CircularProgress, Link, Divider } from '@mui/material'
import { ContentCopy as CopyIcon, CheckCircle as ApprovedIcon, HourglassEmpty as PendingIcon, Cancel as RejectedIcon, UploadFile as UploadIcon } from '@mui/icons-material'
import { useAuth } from '../App'
import axios from 'axios'

export default function Profile() {
  const { user, refreshUser } = useAuth()
  
  const [displayName, setDisplayName] = useState(user?.display_name || '')
  const [avatarUrl, setAvatarUrl] = useState(user?.avatar_url || '')
  const [emailNotif, setEmailNotif] = useState(user?.notification_preferences?.email ?? true)
  const [inAppNotif, setInAppNotif] = useState(user?.notification_preferences?.in_app ?? true)
  
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  
  const [profileError, setProfileError] = useState('')
  const [pwdError, setPwdError] = useState('')
  
  const [openSnackbar, setOpenSnackbar] = useState(false)
  const [snackbarMsg, setSnackbarMsg] = useState('')
  const [loadingProfile, setLoadingProfile] = useState(false)
  const [loadingPwd, setLoadingPwd] = useState(false)

  // Payment states
  const [pixConfig, setPixConfig] = useState(null)
  const [qrBlobUrl, setQrBlobUrl] = useState('')
  const [pixKeyReceive, setPixKeyReceive] = useState(user?.pix_key_receive || '')
  const [proofFile, setProofFile] = useState(null)
  const [uploadError, setUploadError] = useState('')
  const [uploadSuccess, setUploadSuccess] = useState('')
  const [uploading, setUploading] = useState(false)
  const [loadingPix, setLoadingPix] = useState(true)

  const loadPixData = async () => {
    try {
      setLoadingPix(true)
      const configRes = await axios.get('/api/payments/config')
      setPixConfig(configRes.data)
      
      if (configRes.data && configRes.data.pix_key) {
        const qrRes = await axios.get('/api/payments/qrcode', { responseType: 'blob' })
        const url = URL.createObjectURL(qrRes.data)
        setQrBlobUrl(url)
      }
    } catch (err) {
      console.error("Erro ao carregar dados do Pix:", err)
    } finally {
      setLoadingPix(false)
    }
  }

  useEffect(() => {
    loadPixData()
  }, [])

  const handleCopyCopiaCola = () => {
    if (pixConfig?.copia_e_cola) {
      navigator.clipboard.writeText(pixConfig.copia_e_cola)
      setSnackbarMsg('Código Pix Copia e Cola copiado!')
      setOpenSnackbar(true)
    }
  }

  const handleUploadProof = async (e) => {
    e.preventDefault()
    setUploadError('')
    setUploadSuccess('')
    
    if (!pixKeyReceive.trim()) {
      setUploadError('Por favor, informe sua chave PIX para recebimento de eventuais prêmios.')
      return
    }
    
    if (!proofFile) {
      setUploadError('Por favor, selecione um arquivo de comprovante.')
      return
    }
    
    if (proofFile.size > 1024 * 1024) {
      setUploadError('O arquivo do comprovante não pode exceder 1MB de tamanho.')
      return
    }
    
    const ext = proofFile.name.split('.').pop().toLowerCase()
    if (!['png', 'jpg', 'jpeg', 'pdf'].includes(ext)) {
      setUploadError('Formato inválido. Apenas arquivos PNG, JPG, JPEG e PDF são aceitos.')
      return
    }
    
    setUploading(true)
    const formData = new FormData()
    formData.append('file', proofFile)
    formData.append('pix_key_receive', pixKeyReceive)
    
    try {
      await axios.post('/api/payments/submit-proof', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setUploadSuccess('Comprovante de pagamento enviado com sucesso!')
      await refreshUser()
      loadPixData()
    } catch (err) {
      setUploadError(err.response?.data?.detail || 'Erro ao enviar comprovante.')
    } finally {
      setUploading(false)
    }
  }

  const handleUpdateProfile = async (e) => {
    e.preventDefault()
    setProfileError('')
    setLoadingProfile(true)

    try {
      await axios.put('/api/auth/me', {
        display_name: displayName,
        avatar_url: avatarUrl || null,
        notification_preferences: {
          email: emailNotif,
          in_app: inAppNotif
        }
      })
      await refreshUser()
      setSnackbarMsg('Perfil atualizado com sucesso!')
      setOpenSnackbar(true)
    } catch (err) {
      setProfileError(err.response?.data?.detail || 'Erro ao atualizar dados do perfil.')
    } finally {
      setLoadingProfile(false)
    }
  }

  const handleUpdatePassword = async (e) => {
    e.preventDefault()
    setPwdError('')

    if (password.length < 6) {
      setPwdError('A nova senha deve conter no mínimo 6 caracteres.')
      return
    }
    if (password !== confirmPassword) {
      setPwdError('As senhas não coincidem.')
      return
    }

    setLoadingPwd(true)

    try {
      await axios.put('/api/auth/me', {
        password: password
      })
      setPassword('')
      setConfirmPassword('')
      setSnackbarMsg('Senha atualizada com sucesso!')
      setOpenSnackbar(true)
    } catch (err) {
      setPwdError(err.response?.data?.detail || 'Erro ao atualizar senha.')
    } finally {
      setLoadingPwd(false)
    }
  }

  return (
    <Box sx={{ maxWidth: 800, mx: 'auto', mt: 2 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 3 }}>
        Minha Conta
      </Typography>

      <Grid container spacing={3}>
        {/* Left Side: Avatar Preview and Profile Info */}
        <Grid item xs={12} md={7}>
          <Card sx={{ height: '100%' }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                Dados Cadastrais
              </Typography>
              
              {profileError && (
                <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>
                  {profileError}
                </Alert>
              )}

              <Box component="form" onSubmit={handleUpdateProfile}>
                <Stack spacing={3}>
                  <Box display="flex" alignItems="center" gap={3}>
                    <Avatar 
                      src={avatarUrl || ''} 
                      alt={displayName} 
                      sx={{ width: 80, height: 80, bgcolor: 'secondary.main', color: 'secondary.contrastText', fontSize: '2rem', fontWeight: 'bold' }}
                    >
                      {displayName.charAt(0).toUpperCase()}
                    </Avatar>
                    <TextField
                      label="URL do Avatar (opcional)"
                      variant="outlined"
                      fullWidth
                      value={avatarUrl}
                      onChange={(e) => setAvatarUrl(e.target.value)}
                      placeholder="https://exemplo.com/avatar.jpg"
                    />
                  </Box>

                  <TextField
                    label="Nome de usuário (Username)"
                    variant="outlined"
                    fullWidth
                    disabled
                    value={user?.username || ''}
                    helperText="O nome de usuário não pode ser alterado."
                  />

                  <TextField
                    label="E-mail corporativo / pessoal"
                    variant="outlined"
                    fullWidth
                    disabled
                    value={user?.email || ''}
                    helperText="O e-mail não pode ser alterado."
                  />

                  <TextField
                    label="Nome de exibição (Display Name)"
                    variant="outlined"
                    fullWidth
                    required
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                  />

                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mt: 1 }}>
                    Preferências de Notificação
                  </Typography>
                  <Stack direction="row" spacing={3}>
                    <FormControlLabel
                      control={
                        <Checkbox 
                          checked={emailNotif} 
                          onChange={(e) => setEmailNotif(e.target.checked)} 
                          color="primary"
                        />
                      }
                      label="Receber e-mails"
                    />
                    <FormControlLabel
                      control={
                        <Checkbox 
                          checked={inAppNotif} 
                          onChange={(e) => setInAppNotif(e.target.checked)} 
                          color="primary"
                        />
                      }
                      label="Alertas na plataforma"
                    />
                  </Stack>

                  <Button
                    type="submit"
                    variant="contained"
                    color="primary"
                    disabled={loadingProfile}
                    sx={{ alignSelf: 'flex-start', mt: 2 }}
                  >
                    {loadingProfile ? 'Salvando...' : 'Salvar Alterações'}
                  </Button>
                </Stack>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Right Side: Password Update & Payment Verification */}
        <Grid item xs={12} md={5}>
          <Stack spacing={3}>
            {/* Alterar Senha */}
            <Card>
              <CardContent sx={{ p: 4 }}>
                <Typography variant="h6" gutterBottom sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                  Alterar Senha
                </Typography>
                
                {pwdError && (
                  <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>
                    {pwdError}
                  </Alert>
                )}

                <Box component="form" onSubmit={handleUpdatePassword}>
                  <Stack spacing={3}>
                    <TextField
                      label="Nova Senha"
                      type="password"
                      variant="outlined"
                      fullWidth
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      helperText="Mínimo de 6 caracteres."
                    />
                    <TextField
                      label="Confirmar Nova Senha"
                      type="password"
                      variant="outlined"
                      fullWidth
                      required
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                    />

                    <Button
                      type="submit"
                      variant="contained"
                      color="secondary"
                      disabled={loadingPwd}
                      sx={{ alignSelf: 'flex-start', mt: 1 }}
                    >
                      {loadingPwd ? 'Alterando...' : 'Alterar Senha'}
                    </Button>
                  </Stack>
                </Box>
              </CardContent>
            </Card>

            {/* Pagamento e Participação */}
            <Card>
              <CardContent sx={{ p: 4 }}>
                <Typography variant="h6" gutterBottom sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  💳 Taxa de Inscrição e Pagamento
                </Typography>
                <Divider sx={{ mb: 3 }} />

                {loadingPix ? (
                  <Box display="flex" justifyContent="center" alignItems="center" py={3}>
                    <CircularProgress size={30} />
                  </Box>
                ) : !pixConfig || !pixConfig.pix_key ? (
                  <Alert severity="warning" sx={{ borderRadius: 2 }}>
                    Aguardando definição dos dados de pagamento Pix pelo administrador.
                  </Alert>
                ) : (
                  <Stack spacing={3}>
                    {/* Status do pagamento do usuário */}
                    {user?.payment_status === 'approved' && (
                      <Alert severity="success" icon={<ApprovedIcon />} sx={{ borderRadius: 2, fontWeight: 600 }}>
                        Pagamento aprovado. Seus palpites estão totalmente liberados!
                      </Alert>
                    )}

                    {user?.payment_status === 'submitted' && (
                      <Alert severity="warning" icon={<PendingIcon />} sx={{ borderRadius: 2, fontWeight: 600 }}>
                        Comprovante enviado! Aguardando aprovação pelo administrador.
                      </Alert>
                    )}

                    {user?.payment_status === 'rejected' && (
                      <Alert severity="error" icon={<RejectedIcon />} sx={{ borderRadius: 2 }}>
                        <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>
                          Pagamento recusado
                        </Typography>
                        Motivo: <strong>{user?.payment_rejected_reason || 'Nenhuma justificativa fornecida.'}</strong>.
                        Por favor, envie um novo comprovante correto.
                      </Alert>
                    )}

                    {user?.payment_status === 'pending' && (
                      <Alert severity="info" sx={{ borderRadius: 2 }}>
                        Efetue o pagamento da taxa de inscrição para poder enviar seus palpites de partidas.
                      </Alert>
                    )}

                    {/* QR Code and Copy Paste */}
                    <Box sx={{ border: '1px solid #1f2937', borderRadius: 3, p: 2, bgcolor: 'rgba(255,255,255,0.01)', textAlign: 'center' }}>
                      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1, fontWeight: 600 }}>
                        Taxa de Inscrição: R$ {pixConfig.entry_fee.toFixed(2)}
                      </Typography>

                      {qrBlobUrl && (
                        <Box sx={{ display: 'flex', justifyContent: 'center', my: 2 }}>
                          <Box sx={{ bgcolor: 'white', p: 1.5, borderRadius: 3, display: 'inline-block' }}>
                            <img src={qrBlobUrl} alt="Pix QR Code" style={{ width: 180, height: 180, display: 'block' }} />
                          </Box>
                        </Box>
                      )}

                      {pixConfig.copia_e_cola && (
                        <Button 
                          variant="outlined" 
                          color="primary" 
                          size="small" 
                          startIcon={<CopyIcon />} 
                          onClick={handleCopyCopiaCola}
                          sx={{ mt: 1, textTransform: 'none', borderRadius: 2 }}
                        >
                          Copiar Código Pix Copia e Cola
                        </Button>
                      )}
                    </Box>

                    {/* Submit Proof Form */}
                    <Box component="form" onSubmit={handleUploadProof}>
                      <Stack spacing={2.5}>
                        {uploadError && <Alert severity="error" sx={{ borderRadius: 2 }}>{uploadError}</Alert>}
                        {uploadSuccess && <Alert severity="success" sx={{ borderRadius: 2 }}>{uploadSuccess}</Alert>}

                        <TextField
                          label="Sua Chave Pix para Recebimento de Prêmio"
                          variant="outlined"
                          required
                          fullWidth
                          value={pixKeyReceive}
                          onChange={(e) => setPixKeyReceive(e.target.value)}
                          placeholder="Chave Pix (ex: Celular, E-mail, CPF)"
                          disabled={user?.payment_status === 'approved' || user?.payment_status === 'submitted'}
                          helperText="Caso você termine nas primeiras colocações, utilizaremos essa chave para enviar a premiação."
                        />

                        {user?.payment_status !== 'approved' && user?.payment_status !== 'submitted' ? (
                          <Stack spacing={1.5}>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                              Selecionar Comprovante (PNG, JPG, JPEG ou PDF de até 1MB)
                            </Typography>
                            
                            <Button
                              variant="outlined"
                              component="label"
                              color="secondary"
                              startIcon={<UploadIcon />}
                              sx={{ textTransform: 'none', borderRadius: 2, py: 1 }}
                            >
                              {proofFile ? proofFile.name : 'Selecionar Arquivo...'}
                              <input
                                type="file"
                                hidden
                                accept=".png,.jpg,.jpeg,.pdf"
                                onChange={(e) => setProofFile(e.target.files[0])}
                              />
                            </Button>

                            <Button
                              type="submit"
                              variant="contained"
                              color="primary"
                              disabled={uploading}
                              sx={{ py: 1, mt: 1, borderRadius: 2 }}
                            >
                              {uploading ? 'Enviando comprovante...' : 'Enviar Comprovante de Pagamento'}
                            </Button>
                          </Stack>
                        ) : (
                          user?.payment_status === 'submitted' && (
                            <Box textAlign="center" py={1.5}>
                              <Typography variant="body2" color="warning.main" sx={{ fontWeight: 600 }}>
                                📁 Arquivo enviado com sucesso e sob análise.
                              </Typography>
                              <Link href="/api/payments/proof/me" target="_blank" rel="noopener" sx={{ display: 'inline-block', mt: 1, fontSize: '0.85rem' }}>
                                Visualizar comprovante enviado
                              </Link>
                            </Box>
                          )
                        )}
                      </Stack>
                    </Box>
                  </Stack>
                )}
              </CardContent>
            </Card>
          </Stack>
        </Grid>
      </Grid>

      {/* Success Snackbar */}
      <Snackbar
        open={openSnackbar}
        autoHideDuration={4000}
        onClose={() => setOpenSnackbar(false)}
        message={snackbarMsg}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </Box>
  )
}
