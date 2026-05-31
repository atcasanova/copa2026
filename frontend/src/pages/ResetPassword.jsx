import React, { useState } from 'react'
import { useNavigate, Link as RouterLink, useSearchParams } from 'react-router-dom'
import { Box, Card, CardContent, TextField, Button, Typography, Link, Alert, Stack } from '@mui/material'
import axios from 'axios'

export default function ResetPassword() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  const handleRequestReset = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setLoading(true)

    try {
      const res = await axios.post('/api/auth/password-reset/request', { email: email.trim() })
      setSuccess(res.data.message || 'Se o e-mail estiver cadastrado, enviaremos um link de redefinição.')
    } catch (err) {
      setError(err.response?.data?.detail || 'Não foi possível solicitar a redefinição de senha.')
    } finally {
      setLoading(false)
    }
  }

  const handleConfirmReset = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')

    if (password.length < 6) {
      setError('A nova senha deve conter no mínimo 6 caracteres.')
      return
    }
    if (password !== confirmPassword) {
      setError('As senhas não coincidem.')
      return
    }

    setLoading(true)
    try {
      await axios.post('/api/auth/password-reset/confirm', { token, password })
      setSuccess('Senha redefinida com sucesso. Redirecionando para o login...')
      setTimeout(() => navigate('/login', { replace: true }), 2000)
    } catch (err) {
      setError(err.response?.data?.detail || 'Token inválido ou expirado.')
    } finally {
      setLoading(false)
    }
  }

  const isConfirming = Boolean(token)

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'background.default',
        background: 'radial-gradient(circle, rgba(16,185,129,0.08) 0%, rgba(11,15,25,1) 70%)',
        p: 2
      }}
    >
      <Card sx={{ maxWidth: 480, width: '100%', borderRadius: 4, boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.4)' }}>
        <CardContent sx={{ p: { xs: 3, sm: 5 } }}>
          <Stack spacing={3} alignItems="center">
            <Box textAlign="center">
              <Typography variant="h4" component="h1" sx={{ fontWeight: 800, fontFamily: 'Outfit', color: 'primary.main' }}>
                Redefinir Senha
              </Typography>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1 }}>
                {isConfirming ? 'Informe uma nova senha para sua conta.' : 'Informe o e-mail cadastrado para receber o link.'}
              </Typography>
            </Box>

            {error && <Alert severity="error" sx={{ width: '100%', borderRadius: 2 }}>{error}</Alert>}
            {success && <Alert severity="success" sx={{ width: '100%', borderRadius: 2 }}>{success}</Alert>}

            <Box component="form" onSubmit={isConfirming ? handleConfirmReset : handleRequestReset} sx={{ width: '100%' }}>
              <Stack spacing={2.5}>
                {isConfirming ? (
                  <>
                    <TextField
                      label="Nova senha"
                      type="password"
                      variant="outlined"
                      fullWidth
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete="new-password"
                    />
                    <TextField
                      label="Confirmar nova senha"
                      type="password"
                      variant="outlined"
                      fullWidth
                      required
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      autoComplete="new-password"
                    />
                  </>
                ) : (
                  <TextField
                    label="E-mail"
                    type="email"
                    variant="outlined"
                    fullWidth
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="email"
                  />
                )}

                <Button
                  type="submit"
                  variant="contained"
                  color="primary"
                  size="large"
                  fullWidth
                  disabled={loading}
                  sx={{ py: 1.5, fontSize: '1rem', fontWeight: 'bold' }}
                >
                  {loading ? 'Processando...' : (isConfirming ? 'Salvar Nova Senha' : 'Enviar Link de Redefinição')}
                </Button>
              </Stack>
            </Box>

            <Typography variant="body2" color="text.secondary" align="center">
              <Link component={RouterLink} to="/login" color="primary.main" sx={{ fontWeight: 600, textDecoration: 'none' }}>
                Voltar para o login
              </Link>
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  )
}
