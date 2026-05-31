import React, { useState } from 'react'
import { useNavigate, Link as RouterLink } from 'react-router-dom'
import { Box, Card, CardContent, TextField, Button, Typography, Link, Alert, Stack } from '@mui/material'
import axios from 'axios'
import { useAuth } from '../App'

export default function Login() {
  const { setToken } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    // Form data encoding
    const params = new URLSearchParams()
    params.append('username', username)
    params.append('password', password)

    try {
      const res = await axios.post('/api/auth/login', params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      })
      setToken(res.data.access_token)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Falha ao autenticar. Verifique seus dados.')
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
      <Card sx={{ maxWidth: 450, width: '100%', borderRadius: 4, boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.4)' }}>
        <CardContent sx={{ p: { xs: 3, sm: 5 } }}>
          <Stack spacing={3} alignItems="center">
            <Typography variant="h3" sx={{ fontSize: '3rem', fontWeight: 900, textAlign: 'center' }}>
              ⚽
            </Typography>
            <Box textAlign="center">
              <Typography variant="h4" component="h1" sx={{ fontWeight: 800, fontFamily: 'Outfit', color: 'primary.main' }}>
                Futebol Pool 2026
              </Typography>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1 }}>
                Faça o login para palpitar na Copa do Mundo
              </Typography>
            </Box>

            {error && (
              <Alert severity="error" sx={{ width: '100%', borderRadius: 2 }}>
                {error}
              </Alert>
            )}

            <Box component="form" onSubmit={handleSubmit} sx={{ width: '100%' }}>
              <Stack spacing={2.5}>
                <TextField
                  label="Nome de usuário"
                  variant="outlined"
                  fullWidth
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                />
                <TextField
                  label="Senha"
                  type="password"
                  variant="outlined"
                  fullWidth
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                />

                {/* Password reset placeholder */}
                <Box display="flex" justifyContent="flex-end">
                  <Link
                    component="button"
                    type="button"
                    variant="caption"
                    color="secondary.main"
                    onClick={() => alert("A redefinição de senha estará disponível em uma atualização futura. Contate o administrador do sistema.")}
                    sx={{ textDecoration: 'none', fontWeight: 600 }}
                  >
                    Esqueceu sua senha?
                  </Link>
                </Box>

                <Button
                  type="submit"
                  variant="contained"
                  color="primary"
                  size="large"
                  fullWidth
                  disabled={loading}
                  sx={{ py: 1.5, fontSize: '1rem', fontWeight: 'bold' }}
                >
                  {loading ? 'Entrando...' : 'Entrar no Bolão'}
                </Button>
              </Stack>
            </Box>

            <Typography variant="body2" color="text.secondary" align="center">
              Ainda não tem conta?{' '}
              <Link component={RouterLink} to="/register" color="primary.main" sx={{ fontWeight: 600, textDecoration: 'none' }}>
                Cadastre-se aqui
              </Link>
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  )
}
