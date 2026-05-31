import React, { useState, useEffect } from 'react'
import { useNavigate, Link as RouterLink } from 'react-router-dom'
import {
  Box, Card, CardContent, Grid, Typography, Button, TextField,
  FormControlLabel, Checkbox, Stack, List, ListItem, ListItemText,
  Divider, Alert, Chip, IconButton, Snackbar
} from '@mui/material'
import {
  AddCircleOutline as CreateIcon,
  Input as JoinIcon,
  Lock as LockIcon,
  Public as PublicIcon,
  ChevronRight as ArrowIcon
} from '@mui/icons-material'
import axios from 'axios'

export default function Groups() {
  const navigate = useNavigate()
  
  // Data lists
  const [groups, setGroups] = useState([])
  
  // Form fields
  const [createName, setCreateName] = useState('')
  const [createDesc, setCreateDesc] = useState('')
  const [createPrivate, setCreatePrivate] = useState(false)
  
  const [joinCode, setJoinCode] = useState('')
  
  // UI States
  const [error, setError] = useState('')
  const [openSnackbar, setOpenSnackbar] = useState(false)
  const [snackbarMsg, setSnackbarMsg] = useState('')
  const [loading, setLoading] = useState(true)

  const loadGroups = async () => {
    try {
      setLoading(true)
      const res = await axios.get('/api/groups')
      setGroups(res.data)
    } catch (err) {
      setError('Erro ao carregar os grupos.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadGroups()
  }, [])

  const handleCreateGroup = async (e) => {
    e.preventDefault()
    setError('')
    if (createName.trim().length < 3) {
      setError('O nome do grupo deve conter pelo menos 3 caracteres.')
      return
    }

    try {
      const res = await axios.post('/api/groups', {
        name: createName.trim(),
        description: createDesc.trim() || null,
        is_private: createPrivate
      })
      
      setCreateName('')
      setCreateDesc('')
      setCreatePrivate(false)
      
      setSnackbarMsg('Grupo criado com sucesso!')
      setOpenSnackbar(true)
      
      // Navigate to details
      navigate(`/groups/${res.data.id}`)
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao criar o grupo.')
    }
  }

  const handleJoinByCode = async (e) => {
    e.preventDefault()
    setError('')
    if (!joinCode.trim()) return

    try {
      const res = await axios.post(`/api/groups/join/code/${joinCode.trim().toUpperCase()}`)
      setJoinCode('')
      
      const isApproved = res.data.is_approved
      setSnackbarMsg(isApproved ? 'Você entrou no grupo!' : 'Solicitação de entrada enviada com sucesso!')
      setOpenSnackbar(true)
      
      loadGroups()
    } catch (err) {
      setError(err.response?.data?.detail || 'Código de convite inválido ou expirado.')
    }
  }

  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 3 }}>
        👥 Grupos e Ligas
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>{error}</Alert>}

      <Grid container spacing={3}>
        {/* Left Side: Create and Join actions */}
        <Grid item xs={12} md={4}>
          <Stack spacing={3}>
            {/* Create Group Form */}
            <Card>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <CreateIcon color="primary" /> Criar Novo Grupo
                </Typography>
                <Divider sx={{ mb: 2 }} />
                <Box component="form" onSubmit={handleCreateGroup}>
                  <Stack spacing={2}>
                    <TextField
                      label="Nome do Grupo"
                      variant="outlined"
                      size="small"
                      fullWidth
                      required
                      value={createName}
                      onChange={(e) => setCreateName(e.target.value)}
                    />
                    <TextField
                      label="Descrição (opcional)"
                      variant="outlined"
                      size="small"
                      fullWidth
                      multiline
                      rows={2}
                      value={createDesc}
                      onChange={(e) => setCreateDesc(e.target.value)}
                    />
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={createPrivate}
                          onChange={(e) => setCreatePrivate(e.target.checked)}
                          color="primary"
                        />
                      }
                      label="Grupo Privado (Requer aprovação)"
                    />
                    <Button type="submit" variant="contained" color="primary" fullWidth>
                      Criar Grupo
                    </Button>
                  </Stack>
                </Box>
              </CardContent>
            </Card>

            {/* Join Group Form */}
            <Card>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <JoinIcon color="secondary" /> Entrar por Código
                </Typography>
                <Divider sx={{ mb: 2 }} />
                <Box component="form" onSubmit={handleJoinByCode}>
                  <Stack spacing={2}>
                    <TextField
                      label="Código de Convite"
                      variant="outlined"
                      size="small"
                      fullWidth
                      required
                      placeholder="Ex: A1B2C3D4"
                      value={joinCode}
                      onChange={(e) => setJoinCode(e.target.value)}
                    />
                    <Button type="submit" variant="outlined" color="secondary" fullWidth>
                      Entrar no Grupo
                    </Button>
                  </Stack>
                </Box>
              </CardContent>
            </Card>
          </Stack>
        </Grid>

        {/* Right Side: Groups List */}
        <Grid item xs={12} md={8}>
          <Card sx={{ height: '100%' }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                📋 Meus Grupos e Ligas Disponíveis
              </Typography>
              <Divider sx={{ mb: 3 }} />

              {loading ? (
                <Typography color="text.secondary">Carregando grupos...</Typography>
              ) : groups.length === 0 ? (
                <Alert severity="info" sx={{ borderRadius: 2 }}>
                  Você ainda não participa de nenhum grupo. Crie um grupo ou digite um código de convite ao lado.
                </Alert>
              ) : (
                <Grid container spacing={2}>
                  {groups.map((group) => (
                    <Grid item xs={12} sm={6} key={group.id}>
                      <Card 
                        sx={{ 
                          height: '100%',
                          display: 'flex', 
                          flexDirection: 'column', 
                          justifyContent: 'space-between',
                          borderColor: '#1f2937',
                          cursor: 'pointer',
                          '&:hover': {
                            borderColor: 'primary.main',
                            transform: 'translateY(-1px)',
                            boxShadow: '0 4px 12px rgba(16,185,129,0.1)'
                          },
                          transition: 'all 0.2s'
                        }}
                        onClick={() => navigate(`/groups/${group.id}`)}
                      >
                        <CardContent sx={{ p: 3 }}>
                          <Box display="flex" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 1 }}>
                            <Typography variant="subtitle1" sx={{ fontWeight: 700, fontFamily: 'Outfit' }}>
                              {group.name}
                            </Typography>
                            {group.is_private ? (
                              <Chip size="small" icon={<LockIcon />} label="Privado" color="warning" variant="outlined" />
                            ) : (
                              <Chip size="small" icon={<PublicIcon />} label="Público" color="success" variant="outlined" />
                            )}
                          </Box>
                          
                          <Typography variant="body2" color="text.secondary" sx={{ minHeight: 40, mb: 2, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                            {group.description || 'Sem descrição.'}
                          </Typography>
                          
                          <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mt: 'auto' }}>
                            <Typography variant="caption" color="text.secondary">
                              Dono: {group.owner?.display_name || 'Desconhecido'}
                            </Typography>
                            <IconButton size="small" color="primary">
                              <ArrowIcon />
                            </IconButton>
                          </Box>
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Snackbar */}
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
