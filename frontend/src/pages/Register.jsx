import React, { useEffect, useState } from 'react'
import { useNavigate, Link as RouterLink, useSearchParams } from 'react-router-dom'
import { Box, Card, CardContent, TextField, Button, Typography, Link, Alert, Stack } from '@mui/material'
import axios from 'axios'

export default function Register() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [inviteCode] = useState(searchParams.get('code') || '')
  const [registrationCode] = useState(searchParams.get('access') || '')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [inviteError, setInviteError] = useState('')
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)
  const [checkingInvite, setCheckingInvite] = useState(true)

  useEffect(() => {
    const checkInvite = async () => {
      if (registrationCode) {
        try {
          const res = await axios.get(`/api/auth/registration-link/check?code=${encodeURIComponent(registrationCode)}`)
          if (!res.data.valid) {
            setInviteError(res.data.detail || 'Link de cadastro inválido.')
          }
        } catch (err) {
          setInviteError('Não foi possível validar este link de cadastro.')
        } finally {
          setCheckingInvite(false)
        }
        return
      }

      if (!inviteCode) {
        setInviteError('O cadastro é permitido apenas por convite ou link autorizado.')
        setCheckingInvite(false)
        return
      }

      try {
        const res = await axios.get(`/api/auth/invitations/check?code=${encodeURIComponent(inviteCode)}`)
        if (!res.data.valid) {
          setInviteError(res.data.detail || 'Convite inválido ou já utilizado.')
          return
        }
        setEmail(res.data.email || '')
      } catch (err) {
        setInviteError('Não foi possível validar este convite.')
      } finally {
        setCheckingInvite(false)
      }
    }

    checkInvite()
  }, [inviteCode, registrationCode])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (inviteError || (!inviteCode && !registrationCode)) {
      setError('Use um link válido para concluir o cadastro.')
      return
    }

    // Basic password validation
    if (password.length < 6) {
      setError('A senha deve conter no mínimo 6 caracteres.')
      return
    }
    if (password !== confirmPassword) {
      setError('As senhas não coincidem.')
      return
    }

    setLoading(true)

    try {
      const queryParam = inviteCode
        ? `invite_code=${encodeURIComponent(inviteCode)}`
        : `registration_code=${encodeURIComponent(registrationCode)}`
      await axios.post(`/api/auth/register?${queryParam}`, {
        username: username.trim(),
        email: email.trim(),
        display_name: displayName.trim(),
        password
      })
      setSuccess(true)
      setTimeout(() => {
        navigate('/login')
      }, 2500)
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao realizar cadastro. Tente outro nome de usuário ou e-mail.')
    } finally {
      setLoading(false)
    }
  }

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
      <Card sx={{ maxWidth: 500, width: '100%', borderRadius: 4, boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.4)' }}>
        <CardContent sx={{ p: { xs: 3, sm: 5 } }}>
          <Stack spacing={3} alignItems="center">
            <Box textAlign="center">
              <Typography variant="h4" component="h1" sx={{ fontWeight: 800, fontFamily: 'Outfit', color: 'primary.main' }}>
                Criar Nova Conta
              </Typography>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1 }}>
              {registrationCode ? 'Complete seu cadastro para acessar o bolão.' : 'Complete seu cadastro usando o convite recebido por e-mail.'}
              </Typography>
            </Box>

            {checkingInvite && (
              <Alert severity="info" sx={{ width: '100%', borderRadius: 2 }}>
                Validando convite...
              </Alert>
            )}

            {inviteError && (
              <Alert severity="warning" sx={{ width: '100%', borderRadius: 2 }}>
                {inviteError}
              </Alert>
            )}

            {error && (
              <Alert severity="error" sx={{ width: '100%', borderRadius: 2 }}>
                {error}
              </Alert>
            )}

            {success && (
              <Alert severity="success" sx={{ width: '100%', borderRadius: 2 }}>
                Cadastro realizado com sucesso! Redirecionando para login...
              </Alert>
            )}

            {!inviteError && (
            <Box component="form" onSubmit={handleSubmit} sx={{ width: '100%' }}>
              <Stack spacing={2}>
                <TextField
                  label="Nome de usuário (Username)"
                  variant="outlined"
                  fullWidth
                  required
                  disabled={success}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="ex: joaosilva"
                />
                <TextField
                  label="Nome exibido (Display Name)"
                  variant="outlined"
                  fullWidth
                  required
                  disabled={success}
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="ex: João Silva"
                />
                <TextField
                  label="E-mail"
                  type="email"
                  variant="outlined"
                  fullWidth
                  required
                  disabled={!registrationCode}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={registrationCode ? 'seu@email.com' : 'E-mail vinculado ao convite'}
                />
                <TextField
                  label="Senha"
                  type="password"
                  variant="outlined"
                  fullWidth
                  required
                  disabled={success}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <TextField
                  label="Confirmar Senha"
                  type="password"
                  variant="outlined"
                  fullWidth
                  required
                  disabled={success}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />

                <Button
                  type="submit"
                  variant="contained"
                  color="primary"
                  size="large"
                  fullWidth
                  disabled={loading || success || checkingInvite}
                  sx={{ py: 1.5, mt: 1, fontSize: '1rem', fontWeight: 'bold' }}
                >
                  {loading ? 'Cadastrando...' : 'Cadastrar'}
                </Button>
              </Stack>
            </Box>
            )}

            <Typography variant="body2" color="text.secondary" align="center">
              Já possui uma conta?{' '}
              <Link component={RouterLink} to="/login" color="primary.main" sx={{ fontWeight: 600, textDecoration: 'none' }}>
                Faça login
              </Link>
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  )
}
