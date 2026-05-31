import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Box, Card, CardContent, Grid, Typography, Button, TextField, Divider, Alert, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Avatar, Stack,
  Chip, List, ListItem, ListItemText, ListItemSecondaryAction, IconButton, Tooltip
} from '@mui/material'
import {
  ContentCopy as CopyIcon,
  Send as SendIcon,
  Refresh as RefreshIcon,
  Lock as LockIcon,
  Public as PublicIcon,
  AdminPanelSettings as AdminIcon,
  PersonRemove as KickIcon,
  ArrowUpward as PromoteIcon,
  ArrowDownward as DemoteIcon,
  CheckCircle as ApproveIcon,
  Download as ExportIcon
} from '@mui/icons-material'
import axios from 'axios'
import { useAuth } from '../App'

export default function GroupDetails() {
  const { groupId } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()

  const [group, setGroup] = useState(null)
  const [members, setMembers] = useState([])
  const [standings, setStandings] = useState([])
  const [inviteeIdent, setInviteeIdent] = useState('')
  
  // UI states
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  const loadGroupDetails = async () => {
    try {
      setLoading(true)
      setError('')
      
      // Fetch group info
      const groupRes = await axios.get(`/api/groups/${groupId}`)
      setGroup(groupRes.data)
      
      // Fetch group members list
      const membersRes = await axios.get(`/api/groups/${groupId}/members`)
      setMembers(membersRes.data)
      
      // Fetch group standings
      const standingsRes = await axios.get(`/api/rankings/group/${groupId}`)
      setStandings(standingsRes.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao carregar detalhes do grupo.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadGroupDetails()
  }, [groupId])

  const copyInviteCode = () => {
    if (!group) return
    navigator.clipboard.writeText(group.invite_code)
    setSuccessMsg(`Código ${group.invite_code} copiado para a área de transferência!`)
    setTimeout(() => setSuccessMsg(''), 3000)
  }

  const handleSendInvite = async (e) => {
    e.preventDefault()
    setSuccessMsg('')
    setError('')
    if (!inviteeIdent.trim()) return

    try {
      await axios.post(`/api/groups/${groupId}/invite`, {
        invitee_identifier: inviteeIdent.trim()
      })
      setSuccessMsg('Convite enviado com sucesso!')
      setInviteeIdent('')
      loadGroupDetails()
    } catch (err) {
      setError(err.response?.data?.detail || 'Não foi possível convidar o usuário.')
    }
  }

  const handleRegenerateCode = async () => {
    if (!window.confirm('Tem certeza de que deseja invalidar o código antigo e gerar um novo?')) return
    try {
      const res = await axios.post(`/api/groups/${groupId}/invite-code/regenerate`)
      setGroup(prev => ({ ...prev, invite_code: res.data.invite_code }))
      setSuccessMsg('Código de convite regenerado!')
      setTimeout(() => setSuccessMsg(''), 3000)
    } catch (err) {
      setError('Erro ao regenerar código.')
    }
  }

  const handleTogglePrivacy = async () => {
    if (!group) return
    const newPrivate = !group.is_private
    try {
      await axios.post(`/api/groups/${groupId}/privacy?is_private=${newPrivate}`)
      setGroup(prev => ({ ...prev, is_private: newPrivate }))
      setSuccessMsg(`Privacidade do grupo atualizada para ${newPrivate ? 'privado' : 'público'}.`)
      setTimeout(() => setSuccessMsg(''), 3000)
    } catch (err) {
      setError('Erro ao alterar privacidade.')
    }
  }

  const handleApproveMember = async (memberUserId) => {
    try {
      await axios.post(`/api/groups/${groupId}/members/${memberUserId}/approve`)
      loadGroupDetails()
    } catch (err) {
      alert('Erro ao aprovar membro.')
    }
  }

  const handleRemoveMember = async (memberUserId) => {
    if (!window.confirm('Tem certeza de que deseja remover este membro do grupo?')) return
    try {
      await axios.post(`/api/groups/${groupId}/members/${memberUserId}/remove`)
      loadGroupDetails()
    } catch (err) {
      alert(err.response?.data?.detail || 'Erro ao remover membro.')
    }
  }

  const handleChangeMemberRole = async (memberUserId, newRole) => {
    try {
      await axios.post(`/api/groups/${groupId}/members/${memberUserId}/role?new_role=${newRole}`)
      loadGroupDetails()
    } catch (err) {
      alert(err.response?.data?.detail || 'Erro ao alterar função do membro.')
    }
  }

  const handleExportRanking = async () => {
    try {
      const response = await axios.get(`/api/groups/${groupId}/export/ranking`, {
        responseType: 'blob'
      })
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `ranking_grupo_${groupId}.csv`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      alert('Erro ao exportar o ranking do grupo.')
    }
  }

  const handleExportPredictions = async () => {
    try {
      const response = await axios.get(`/api/groups/${groupId}/export/predictions`, {
        responseType: 'blob'
      })
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `palpites_grupo_${groupId}.csv`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      alert('Erro ao exportar os palpites do grupo.')
    }
  }

  if (loading && !group) {
    return <Typography color="text.secondary">Carregando detalhes do grupo...</Typography>
  }

  if (!group) {
    return <Alert severity="error">Grupo não encontrado ou você não tem permissão para acessá-lo.</Alert>
  }

  // Check if current user is owner or admin of this group
  const myMemberRecord = members.find(m => m.user_id === user?.id)
  const isGroupAdmin = myMemberRecord?.role === 'owner' || myMemberRecord?.role === 'admin' || user?.role === 'system_admin'
  const isGroupOwner = myMemberRecord?.role === 'owner' || user?.role === 'system_admin'

  const pendingMembers = members.filter(m => !m.is_approved)
  const approvedMembers = members.filter(m => m.is_approved)

  // Determine top 3 exact score hit medal winners in the group
  const medalWinners = [...standings].sort((a, b) => {
    if (b.exact_scores_count !== a.exact_scores_count) {
      return b.exact_scores_count - a.exact_scores_count
    }
    return standings.indexOf(a) - standings.indexOf(b)
  })

  const getMedal = (userId, exactCount) => {
    if (!exactCount || exactCount === 0) return null
    const idx = medalWinners.findIndex(w => w.user_id === userId)
    if (idx === 0) return { src: '/ouro.png', label: 'Ouro' }
    if (idx === 1) return { src: '/prata.png', label: 'Prata' }
    if (idx === 2) return { src: '/bronze.png', label: 'Bronze' }
    return null
  }

  return (
    <Box sx={{ mt: 1 }}>
      {/* Header Banner */}
      <Card sx={{ mb: 4, background: 'linear-gradient(135deg, rgba(16,185,129,0.1) 0%, rgba(17,24,39,1) 100%)' }}>
        <CardContent sx={{ p: 4 }}>
          <Grid container spacing={3} alignItems="center">
            <Grid item xs={12} sm={8}>
              <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h4" sx={{ fontWeight: 800, fontFamily: 'Outfit' }}>
                  {group.name}
                </Typography>
                {group.is_private ? (
                  <Chip size="small" icon={<LockIcon />} label="Privado" color="warning" />
                ) : (
                  <Chip size="small" icon={<PublicIcon />} label="Público" color="success" />
                )}
              </Stack>
              <Typography variant="body1" color="text.secondary">
                {group.description || 'Sem descrição.'}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                Criado por: <strong>{group.owner?.display_name}</strong> em {new Date(group.created_at).toLocaleDateString('pt-BR')}
              </Typography>
            </Grid>

            {/* Actions for Group Admins */}
            <Grid item xs={12} sm={4} sx={{ textAlign: { sm: 'right' } }}>
              <Stack spacing={1.5} direction={{ xs: 'column', sm: 'row' }} justifyContent={{ sm: 'flex-end' }}>
                <Button 
                  variant="outlined" 
                  startIcon={<ExportIcon />}
                  onClick={handleExportRanking}
                  size="small"
                >
                  Exportar Ranking
                </Button>
                {isGroupAdmin && (
                  <Button 
                    variant="outlined" 
                    color="secondary"
                    startIcon={<ExportIcon />}
                    onClick={handleExportPredictions}
                    size="small"
                  >
                    Exportar Palpites
                  </Button>
                )}
              </Stack>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {successMsg && <Alert severity="success" sx={{ mb: 3, borderRadius: 2 }}>{successMsg}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>{error}</Alert>}

      <Grid container spacing={3}>
        {/* Left Side: Rankings Table */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                🏆 Classificação dos Membros
              </Typography>
              <Divider sx={{ mb: 2 }} />

              <TableContainer component={Paper} sx={{ boxShadow: 'none' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell align="center">Pos</TableCell>
                      <TableCell>Participante</TableCell>
                      <TableCell align="center">Pontos</TableCell>
                      <TableCell align="center">Placares Exatos</TableCell>
                      <TableCell align="center">Resultados</TableCell>
                      <TableCell align="center">Palpites</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {standings.map((row) => {
                      const isMe = row.user_id === user?.id
                      const medal = getMedal(row.user_id, row.exact_scores_count)
                      return (
                        <TableRow 
                          key={row.user_id}
                          sx={{ 
                            bgcolor: isMe ? 'rgba(16, 185, 129, 0.05)' : 'transparent',
                            fontWeight: isMe ? 'bold' : 'normal'
                          }}
                        >
                          <TableCell align="center" sx={{ fontWeight: 800 }}>
                            {row.position}º
                          </TableCell>
                          <TableCell>
                            <Box display="flex" alignItems="center" gap={1.5}>
                              <Avatar src={row.avatar_url || ''} sx={{ width: 28, height: 28 }}>
                                {row.display_name.charAt(0).toUpperCase()}
                              </Avatar>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                {medal && (
                                  <Tooltip title={`${row.exact_scores_count} acertos de placares exatos`}>
                                    <Box 
                                      component="img"
                                      src={medal.src} 
                                      alt={medal.label}
                                      sx={{ 
                                        height: 18, 
                                        width: 18, 
                                        objectFit: 'contain',
                                        cursor: 'pointer',
                                        transition: 'transform 0.2s',
                                        '&:hover': { transform: 'scale(1.25)' }
                                      }} 
                                    />
                                  </Tooltip>
                                )}
                                <Typography variant="body2" sx={{ fontWeight: isMe ? 700 : 500 }}>
                                  {row.display_name} {isMe && '(Você)'}
                                </Typography>
                              </Box>
                            </Box>
                          </TableCell>
                          <TableCell align="center" sx={{ fontWeight: 700, color: 'primary.light' }}>
                            {row.total_points}
                          </TableCell>
                          <TableCell align="center">{row.exact_scores_count}</TableCell>
                          <TableCell align="center">{row.correct_results_count}</TableCell>
                          <TableCell align="center">{row.predictions_count}</TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Right Side: Invites, requests and member actions */}
        <Grid item xs={12} md={4}>
          <Stack spacing={3}>
            {/* Invite Links and Codes */}
            <Card>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2 }}>
                  ✉️ Convidar Amigos
                </Typography>
                <Divider sx={{ mb: 2 }} />

                <Typography variant="caption" color="text.secondary">Código de Convite:</Typography>
                <Box display="flex" alignItems="center" gap={1} sx={{ mt: 0.5, mb: 3 }}>
                  <Typography variant="h5" sx={{ fontWeight: 800, fontFamily: 'Outfit', bgcolor: 'background.default', px: 2, py: 1, borderRadius: 2, border: '1px solid #374151', flexGrow: 1, textAlign: 'center', letterSpacing: 2 }}>
                    {group.invite_code}
                  </Typography>
                  <IconButton color="primary" onClick={copyInviteCode}>
                    <CopyIcon />
                  </IconButton>
                </Box>

                {isGroupAdmin && (
                  <Box component="form" onSubmit={handleSendInvite} sx={{ mb: 3 }}>
                    <Stack direction="row" spacing={1}>
                      <TextField
                        label="Username ou E-mail"
                        variant="outlined"
                        size="small"
                        required
                        fullWidth
                        value={inviteeIdent}
                        onChange={(e) => setInviteeIdent(e.target.value)}
                      />
                      <Button type="submit" variant="contained" color="primary">
                        <SendIcon />
                      </Button>
                    </Stack>
                  </Box>
                )}

                {isGroupAdmin && (
                  <Stack spacing={1}>
                    <Button 
                      variant="outlined" 
                      color="warning" 
                      size="small" 
                      startIcon={<RefreshIcon />}
                      onClick={handleRegenerateCode}
                      fullWidth
                    >
                      Regenerar Código
                    </Button>
                    <Button 
                      variant="outlined" 
                      color="secondary" 
                      size="small"
                      startIcon={group.is_private ? <PublicIcon /> : <LockIcon />}
                      onClick={handleTogglePrivacy}
                      fullWidth
                    >
                      {group.is_private ? 'Tornar Público' : 'Tornar Privado'}
                    </Button>
                  </Stack>
                )}
              </CardContent>
            </Card>

            {/* Pending Requests (Private Groups) */}
            {isGroupAdmin && pendingMembers.length > 0 && (
              <Card sx={{ borderColor: 'warning.main', borderWidth: '1px' }}>
                <CardContent sx={{ p: 3 }}>
                  <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2, color: 'warning.main' }}>
                    ⌛ Solicitações Pendentes ({pendingMembers.length})
                  </Typography>
                  <Divider sx={{ mb: 2 }} />
                  <List disablePadding>
                    {pendingMembers.map((m) => (
                      <ListItem key={m.id} disablePadding sx={{ mb: 1.5, p: 1.5, borderRadius: 2, bgcolor: 'background.default', border: '1px solid #1f2937' }}>
                        <ListItemText 
                          primary={m.user.display_name} 
                          secondary={`@${m.user.username}`} 
                          primaryTypographyProps={{ fontWeight: 600, fontSize: '0.9rem' }}
                        />
                        <ListItemSecondaryAction sx={{ right: 8 }}>
                          <IconButton color="success" size="small" onClick={() => handleApproveMember(m.user_id)}>
                            <ApproveIcon />
                          </IconButton>
                          <IconButton color="error" size="small" onClick={() => handleRemoveMember(m.user_id)}>
                            <KickIcon />
                          </IconButton>
                        </ListItemSecondaryAction>
                      </ListItem>
                    ))}
                  </List>
                </CardContent>
              </Card>
            )}

            {/* Members Settings */}
            <Card>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2 }}>
                  👥 Gerenciar Membros ({approvedMembers.length})
                </Typography>
                <Divider sx={{ mb: 2 }} />
                
                <List disablePadding>
                  {approvedMembers.map((m) => {
                    const self = m.user_id === user?.id
                    return (
                      <ListItem 
                        key={m.id} 
                        disablePadding 
                        sx={{ 
                          mb: 1.5, 
                          p: 1.5, 
                          borderRadius: 2, 
                          bgcolor: 'background.default', 
                          border: '1px solid #1f2937',
                          opacity: m.is_approved ? 1 : 0.6
                        }}
                      >
                        <ListItemText 
                          primary={m.user.display_name} 
                          secondary={
                            m.role === 'owner' ? 'Proprietário' :
                            m.role === 'admin' ? 'Administrador' : 'Membro'
                          } 
                          primaryTypographyProps={{ fontWeight: 600, fontSize: '0.9rem' }}
                          secondaryTypographyProps={{ 
                            color: m.role === 'owner' ? 'secondary.main' : 
                                   m.role === 'admin' ? 'primary.main' : 'text.secondary',
                            fontWeight: 600
                          }}
                        />
                        {isGroupAdmin && !self && m.role !== 'owner' && (
                          <ListItemSecondaryAction sx={{ right: 8 }}>
                            {/* Promote / Demote triggers */}
                            {isGroupOwner && m.role === 'member' && (
                              <Tooltip title="Promover a Admin">
                                <IconButton color="primary" size="small" onClick={() => handleChangeMemberRole(m.user_id, 'admin')}>
                                  <PromoteIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>
                            )}
                            {isGroupOwner && m.role === 'admin' && (
                              <Tooltip title="Rebaixar a Membro">
                                <IconButton color="warning" size="small" onClick={() => handleChangeMemberRole(m.user_id, 'member')}>
                                  <DemoteIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>
                            )}
                            
                            <Tooltip title="Remover do Grupo">
                              <IconButton color="error" size="small" onClick={() => handleRemoveMember(m.user_id)}>
                                <KickIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          </ListItemSecondaryAction>
                        )}
                      </ListItem>
                    )
                  })}
                </List>
              </CardContent>
            </Card>
          </Stack>
        </Grid>
      </Grid>
    </Box>
  )
}
