import React, { useState, useEffect } from 'react'
import {
  Box, Card, CardContent, Typography, Tabs, Tab, Grid, TextField, Button,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  MenuItem, Select, FormControl, InputLabel, Switch, Alert, Snackbar, Stack,
  Divider, Accordion, AccordionSummary, AccordionDetails, Chip, Dialog, DialogTitle, DialogContent, DialogActions
} from '@mui/material'
import {
  ExpandMore as ExpandIcon,
  Save as SaveIcon,
  CloudSync as SyncIcon,
  SportsSoccer as MatchIcon,
  Settings as ConfigIcon,
  Announcement as AnnIcon,
  People as PeopleIcon,
  History as HistoryIcon,
  FileDownload as DownloadIcon,
  Check as CheckIcon,
  Close as CloseIcon,
  Payments as PaymentIcon,
  Mail as MailIcon
} from '@mui/icons-material'
import axios from 'axios'
import { useAuth } from '../App'

export default function AdminPanel() {
  const { user } = useAuth()
  
  // Tabs: 0=Matches, 1=Sync, 2=Config, 3=Announcements, 4=Users, 5=Logs
  const [tabIndex, setTabIndex] = useState(0)
  
  // Shared options
  const [matches, setMatches] = useState([])
  const [stages, setStages] = useState([])
  
  // 0. Matches Management State
  const [filterStage, setFilterStage] = useState('All')
  const [editingMatch, setEditingMatch] = useState(null)
  const [goals1, setGoals1] = useState('')
  const [goals2, setGoals2] = useState('')
  const [etGoals1, setEtGoals1] = useState('')
  const [etGoals2, setEtGoals2] = useState('')
  const [penGoals1, setPenGoals1] = useState('')
  const [penGoals2, setPenGoals2] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)

  // 1. Sync State
  const [syncDiffs, setSyncDiffs] = useState([])
  const [syncLoading, setSyncLoading] = useState(false)
  const [syncResult, setSyncResult] = useState('')

  // 2. Multipliers State
  const [multipliers, setMultipliers] = useState([])
  const [multHistory, setMultHistory] = useState([])
  const [selectedMultStage, setSelectedMultStage] = useState('')
  const [newMultValue, setNewMultValue] = useState('')
  const [multReason, setMultReason] = useState('')

  // 3. Announcements State
  const [annTitle, setAnnTitle] = useState('')
  const [annBody, setAnnBody] = useState('')
  const [annPriority, setAnnPriority] = useState('low')
  const [annTarget, setAnnTarget] = useState('global')
  const [annTargetGroup, setAnnTargetGroup] = useState('')
  const [groups, setGroups] = useState([])

  // 4. Users State
  const [usersList, setUsersList] = useState([])
  const [userSearch, setUserSearch] = useState('')

  // 5. Audit Logs State
  const [auditLogs, setAuditLogs] = useState([])

  // 6. Payments State
  const [pixKey, setPixKey] = useState('')
  const [pixName, setPixName] = useState('')
  const [pixCity, setPixCity] = useState('')
  const [pixEntryFee, setPixEntryFee] = useState('')
  const [paymentUsers, setPaymentUsers] = useState([])
  const [rejectionUserId, setRejectionUserId] = useState(null)
  const [rejectionReason, setRejectionReason] = useState('')
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false)

  // Invitations State
  const [inviteEmail, setInviteEmail] = useState('')
  const [invitationsList, setInvitationsList] = useState([])
  const [inviting, setInviting] = useState(false)

  // UI status
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(true)

  const loadInitialData = async () => {
    try {
      setLoading(true)
      setError('')
      
      // Load matches
      const matchesRes = await axios.get('/api/matches')
      setMatches(matchesRes.data)
      setStages(['All', ...new Set(matchesRes.data.map(m => m.stage))])

      // Depending on permissions and active tab, fetch other data
      if (user?.role === 'system_admin') {
        // Load multipliers
        const multRes = await axios.get('/api/admin/multipliers')
        setMultipliers(multRes.data)
        
        // Load multiplier history
        const histRes = await axios.get('/api/admin/multipliers/history')
        setMultHistory(histRes.data)

        // Load groups (for announcement targets)
        const groupsRes = await axios.get('/api/groups')
        setGroups(groupsRes.data)

        // Load users list
        const usersRes = await axios.get('/api/admin/users')
        setUsersList(usersRes.data)

        // Load audit logs
        const logsRes = await axios.get('/api/admin/audit-logs')
        setAuditLogs(logsRes.data)

        // Load Pix Config
        const pixConfigRes = await axios.get('/api/payments/config')
        setPixKey(pixConfigRes.data.pix_key || '')
        setPixName(pixConfigRes.data.merchant_name || '')
        setPixCity(pixConfigRes.data.merchant_city || '')
        setPixEntryFee(pixConfigRes.data.entry_fee || '')

        // Load payments list
        const paymentsRes = await axios.get('/api/payments/admin/list')
        setPaymentUsers(paymentsRes.data)

        // Load invitations list
        const invitesRes = await axios.get('/api/admin/invitations')
        setInvitationsList(invitesRes.data)
      }
      
      // Load pending sync diffs
      const diffsRes = await axios.get('/api/admin/sync/diffs')
      setSyncDiffs(diffsRes.data)
      
    } catch (err) {
      setError('Erro ao carregar dados do painel administrativo.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadInitialData()
  }, [tabIndex])

  // Save success message alert
  const showSuccess = (msg) => {
    setSuccess(msg)
    setTimeout(() => setSuccess(''), 3000)
  }

  // ==========================================
  // 0. Matches Actions
  // ==========================================
  const handleEditMatch = (match) => {
    setEditingMatch(match)
    setGoals1(match.score_ft_team1 ?? '')
    setGoals2(match.score_ft_team2 ?? '')
    setEtGoals1(match.score_et_team1 ?? '')
    setEtGoals2(match.score_et_team2 ?? '')
    setPenGoals1(match.score_pen_team1 ?? '')
    setPenGoals2(match.score_pen_team2 ?? '')
    setDialogOpen(true)
  }

  const handleSaveScore = async () => {
    if (goals1 === '' || goals2 === '') {
      alert('Os gols regulamentares (tempo normal) são obrigatórios.')
      return
    }
    
    try {
      let query = `/api/admin/matches/${editingMatch.id}/score?score_ft_team1=${goals1}&score_ft_team2=${goals2}`;
      if (etGoals1 !== '' && etGoals2 !== '') {
        query += `&score_et_team1=${etGoals1}&score_et_team2=${etGoals2}`;
      }
      if (penGoals1 !== '' && penGoals2 !== '') {
        query += `&score_pen_team1=${penGoals1}&score_pen_team2=${penGoals2}`;
      }

      await axios.post(query)
      setDialogOpen(false)
      showSuccess('Placar salvo com sucesso como pendente de revisão!')
      loadInitialData()
    } catch (err) {
      alert('Erro ao salvar placar.')
    }
  }

  const handleConfirmScore = async (matchId) => {
    if (!window.confirm('Confirmar este resultado? Os pontos serão fixados e esta pontuação não será sobrescrita pela sincronização automática.')) return
    try {
      await axios.post(`/api/admin/matches/${matchId}/confirm-score`)
      showSuccess('Placar confirmado pelo administrador com sucesso!')
      loadInitialData()
    } catch (err) {
      alert('Erro ao confirmar placar.')
    }
  }

  const handleStatusChange = async (matchId, newStatus) => {
    try {
      await axios.post(`/api/admin/matches/${matchId}/status?status_str=${newStatus}`)
      showSuccess(`Status da partida atualizado para ${newStatus}.`)
      loadInitialData()
    } catch (err) {
      alert('Erro ao alterar status da partida.')
    }
  }

  // ==========================================
  // 1. Sync Actions
  // ==========================================
  const handleTriggerInitialSeed = async () => {
    if (!window.confirm('Iniciar o Seeding de Dados? Isso importará os times, estádios e tabela original do openfootball.')) return
    setSyncLoading(true)
    setSyncResult('Processando carga de dados iniciais...')
    try {
      const res = await axios.post('/api/admin/sync/seed')
      setSyncResult(JSON.stringify(res.data, null, 2))
      showSuccess('Seeding inicial concluído com sucesso!')
      loadInitialData()
    } catch (err) {
      setSyncResult('Erro no seeding: ' + (err.response?.data?.detail?.msg || err.message))
    } finally {
      setSyncLoading(false)
    }
  }

  const handleTriggerSyncJob = async () => {
    setSyncLoading(true)
    setSyncResult('Executando sincronização com repositório do openfootball...')
    try {
      const res = await axios.post('/api/admin/sync/job')
      setSyncResult(JSON.stringify(res.data, null, 2))
      showSuccess('Sincronização manual executada!')
      loadInitialData()
    } catch (err) {
      setSyncResult('Erro na sincronização: ' + err.message)
    } finally {
      setSyncLoading(false)
    }
  }

  const handleApplyDiff = async (diffId) => {
    try {
      await axios.post(`/api/admin/sync/diffs/${diffId}/apply`)
      showSuccess('Alteração de sincronização aplicada no placar!')
      loadInitialData()
    } catch (err) {
      alert('Erro ao aplicar alteração.')
    }
  }

  const handleRejectDiff = async (diffId) => {
    try {
      await axios.post(`/api/admin/sync/diffs/${diffId}/reject`)
      showSuccess('Diferença de sincronização descartada.')
      loadInitialData()
    } catch (err) {
      alert('Erro ao rejeitar diferença.')
    }
  }

  // ==========================================
  // 2. Config Actions
  // ==========================================
  const handleUpdateMultiplier = async (e) => {
    e.preventDefault()
    if (!selectedMultStage || !newMultValue || isNaN(newMultValue) || parseFloat(newMultValue) <= 0) {
      alert('Por favor, informe uma fase válida e um multiplicador positivo.')
      return
    }

    if (!window.confirm('ATENÇÃO: Mudar multiplicadores de fase forçará o recálculo de TODOS os palpites salvos e causará alterações instantâneas no ranking. Deseja prosseguir?')) return

    try {
      await axios.put(`/api/admin/multipliers/${selectedMultStage}`, {
        multiplier: parseFloat(newMultValue),
        reason: multReason.trim() || null
      })
      
      setSelectedMultStage('')
      setNewMultValue('')
      setMultReason('')
      showSuccess('Multiplicador atualizado e apostas recalculadas com sucesso!')
      loadInitialData()
    } catch (err) {
      alert('Erro ao salvar multiplicador.')
    }
  }

  const handleForceRecalculateAll = async () => {
    if (!window.confirm('Forçar recálculo total? Isso irá reprocessar os pontos de cada palpite e classificar novamente o ranking.')) return
    try {
      await axios.post('/api/admin/recalculate-all')
      showSuccess('Recálculo de todas as apostas executado!')
    } catch (err) {
      alert('Erro ao forçar recálculo.')
    }
  }

  // ==========================================
  // 3. Announcement Actions
  // ==========================================
  const handleCreateAnnouncement = async (e) => {
    e.preventDefault()
    if (!annTitle.trim() || !annBody.trim()) return

    try {
      await axios.post('/api/admin/announcements', {
        title: annTitle.trim(),
        body: annBody.trim(),
        priority: annPriority,
        target_type: annTarget,
        target_group_id: annTarget === 'group' ? annTargetGroup : null
      })
      
      setAnnTitle('')
      setAnnBody('')
      setAnnPriority('low')
      setAnnTarget('global')
      setAnnTargetGroup('')
      
      showSuccess('Comunicado publicado com sucesso!')
    } catch (err) {
      alert('Erro ao publicar comunicado.')
    }
  }

  // ==========================================
  // 4. Users Actions
  // ==========================================
  const handleChangeUserRole = async (userId, newRole) => {
    try {
      await axios.post(`/api/admin/users/${userId}/role?role=${newRole}`)
      showSuccess('Função do usuário atualizada com sucesso.')
      loadInitialData()
    } catch (err) {
      alert(err.response?.data?.detail || 'Erro ao alterar função.')
    }
  }

  const handleToggleUserActive = async (userId, currentActive) => {
    try {
      await axios.post(`/api/admin/users/${userId}/status?active=${!currentActive}`)
      showSuccess(`Usuário ${!currentActive ? 'ativado' : 'desativado'} com sucesso.`)
      loadInitialData()
    } catch (err) {
      alert('Erro ao alterar status do usuário.')
    }
  }

  const handleExportCSV = async (type) => {
    try {
      const response = await axios.get(`/api/admin/export/${type}`, {
        responseType: 'blob'
      })
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      let fileName = `${type}_export.csv`
      if (type === 'users') fileName = 'usuarios_export.csv'
      else if (type === 'predictions') fileName = 'apostas_export.csv'
      else if (type === 'scores') fileName = 'placares_export.csv'
      else if (type === 'ranking') fileName = 'ranking_geral_export.csv'
      else if (type === 'audit-logs') fileName = 'auditoria_export.csv'
      link.setAttribute('download', fileName)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      alert('Erro ao exportar arquivo CSV.')
    }
  }

  const formatDateTime = (isoString) => {
    return new Date(isoString).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' })
  }

  // ==========================================
  // 6. Payments Actions
  // ==========================================
  const handleSavePixConfig = async (e) => {
    e.preventDefault()
    try {
      await axios.post('/api/payments/admin/config', {
        pix_key: pixKey,
        merchant_name: pixName,
        merchant_city: pixCity,
        entry_fee: parseFloat(pixEntryFee) || 0.0
      })
      showSuccess('Configuração do Pix salva com sucesso!')
      loadInitialData()
    } catch (err) {
      alert('Erro ao salvar configuração do Pix.')
    }
  }

  const handleApprovePayment = async (userId) => {
    try {
      await axios.post(`/api/payments/admin/approve/${userId}`)
      showSuccess('Pagamento aprovado com sucesso!')
      loadInitialData()
    } catch (err) {
      alert('Erro ao aprovar pagamento.')
    }
  }

  const handleOpenRejectDialog = (userId) => {
    setRejectionUserId(userId)
    setRejectionReason('')
    setRejectDialogOpen(true)
  }

  const handleConfirmRejectPayment = async () => {
    if (!rejectionReason.trim()) {
      alert('Por favor, informe a justificativa da recusa.')
      return
    }
    try {
      const formData = new FormData()
      formData.append('reason', rejectionReason)
      await axios.post(`/api/payments/admin/reject/${rejectionUserId}`, formData)
      showSuccess('Pagamento recusado.')
      setRejectDialogOpen(false)
      loadInitialData()
    } catch (err) {
      alert('Erro ao recusar pagamento.')
    }
  }

  const filteredMatches = matches.filter(m => {
    if (filterStage !== 'All' && m.stage !== filterStage) return false
    return true
  })

  const filteredUsers = usersList.filter(u => {
    if (userSearch.trim()) {
      const s = userSearch.toLowerCase()
      return u.username.toLowerCase().includes(s) || u.display_name.toLowerCase().includes(s) || u.email.toLowerCase().includes(s)
    }
    return true
  })

  const handleSendInvitation = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setInviting(true)
    try {
      await axios.post('/api/admin/invitations', { email: inviteEmail.trim() })
      showSuccess(`Convite enviado com sucesso para ${inviteEmail}!`)
      setInviteEmail('')
      // Reload invitations
      const res = await axios.get('/api/admin/invitations')
      setInvitationsList(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao enviar convite.')
    } finally {
      setInviting(false)
    }
  }

  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 3 }}>
        🛡️ Painel Administrativo
      </Typography>

      {success && <Alert severity="success" sx={{ mb: 3, borderRadius: 2 }}>{success}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>{error}</Alert>}

      <Tabs
        value={tabIndex}
        onChange={(e, val) => setTabIndex(val)}
        textColor="primary"
        indicatorColor="primary"
        variant="scrollable"
        scrollButtons="auto"
        sx={{ borderBottom: 1, borderColor: 'divider', mb: 4 }}
      >
        <Tab icon={<MatchIcon />} label="Placares & Jogos" iconPosition="start" sx={{ fontWeight: 'bold' }} />
        <Tab icon={<SyncIcon />} label="Sincronização" iconPosition="start" sx={{ fontWeight: 'bold' }} />
        {user?.role === 'system_admin' && <Tab icon={<ConfigIcon />} label="Config. Pontuação" iconPosition="start" sx={{ fontWeight: 'bold' }} />}
        {user?.role === 'system_admin' && <Tab icon={<AnnIcon />} label="Publicar Comunicados" iconPosition="start" sx={{ fontWeight: 'bold' }} />}
        {user?.role === 'system_admin' && <Tab icon={<PeopleIcon />} label="Usuários & Acessos" iconPosition="start" sx={{ fontWeight: 'bold' }} />}
        {user?.role === 'system_admin' && <Tab icon={<HistoryIcon />} label="Auditoria & Exportar" iconPosition="start" sx={{ fontWeight: 'bold' }} />}
        {user?.role === 'system_admin' && <Tab icon={<PaymentIcon />} label="Pagamentos" iconPosition="start" sx={{ fontWeight: 'bold' }} />}
        {user?.role === 'system_admin' && <Tab icon={<MailIcon />} label="Convites" iconPosition="start" sx={{ fontWeight: 'bold' }} />}
      </Tabs>

      {/* ==========================================
          TAB 0: MATCHES / SCORE EDITING
         ========================================== */}
      {tabIndex === 0 && (
        <Stack spacing={3}>
          <Card>
            <CardContent sx={{ p: 2 }}>
              <FormControl size="small" sx={{ minWidth: 250 }}>
                <InputLabel>Filtrar por Fase</InputLabel>
                <Select value={filterStage} label="Filtrar por Fase" onChange={(e) => setFilterStage(e.target.value)}>
                  {stages.map(s => (
                    <MenuItem key={s} value={s}>
                      {s === 'All' ? 'Todas as Fases' : s === 'Group Stage' ? 'Fase de Grupos' : s}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </CardContent>
          </Card>

          <TableContainer component={Paper} sx={{ borderRadius: 3 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Fase / ID</TableCell>
                  <TableCell>Partida</TableCell>
                  <TableCell align="center">Placar Cadastrado</TableCell>
                  <TableCell align="center">Status Interno</TableCell>
                  <TableCell align="center">Ações</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredMatches.map(match => (
                  <TableRow key={match.id}>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{match.round}</Typography>
                      <Typography variant="caption" color="text.secondary">ID: #{match.id}</Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>
                        {match.team1_name} x {match.team2_name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">📍 {match.ground}</Typography>
                    </TableCell>
                    <TableCell align="center">
                      {match.score_ft_team1 !== null ? (
                        <Box>
                          <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                            {match.score_ft_team1} - {match.score_ft_team2}
                          </Typography>
                          {match.score_et_team1 !== null && (
                            <Typography variant="caption" color="warning.main" sx={{ display: 'block' }}>
                              Prorrogação: {match.score_et_team1} x {match.score_et_team2}
                            </Typography>
                          )}
                          {match.score_pen_team1 !== null && (
                            <Typography variant="caption" color="info.main" sx={{ display: 'block' }}>
                              Pênaltis: ({match.score_pen_team1} - {match.score_pen_team2})
                            </Typography>
                          )}
                        </Box>
                      ) : (
                        <Typography variant="caption" color="text.secondary">Não registrado</Typography>
                      )}
                    </TableCell>
                    <TableCell align="center">
                      {match.status === 'score_confirmed' ? (
                        <Chip label="Confirmado" color="success" size="small" />
                      ) : match.status === 'score_pending_review' ? (
                        <Chip label="Revisar" color="warning" size="small" />
                      ) : match.status === 'postponed' ? (
                        <Chip label="Adiado" color="error" size="small" />
                      ) : match.status === 'cancelled' ? (
                        <Chip label="Cancelado" color="error" size="small" />
                      ) : (
                        <Chip label="Agendado" variant="outlined" size="small" />
                      )}
                    </TableCell>
                    <TableCell align="center">
                      <Stack direction="row" spacing={1} justifyContent="center">
                        <Button size="small" variant="contained" onClick={() => handleEditMatch(match)}>
                          Definir Placar
                        </Button>
                        {match.status === 'score_pending_review' && (
                          <Button size="small" variant="contained" color="success" startIcon={<CheckIcon />} onClick={() => handleConfirmScore(match.id)}>
                            Confirmar
                          </Button>
                        )}
                        <Select
                          size="small"
                          value={match.status}
                          onChange={(e) => handleStatusChange(match.id, e.target.value)}
                          sx={{ height: 30, fontSize: '0.75rem' }}
                        >
                          <MenuItem value="scheduled">Agendado</MenuItem>
                          <MenuItem value="postponed">Adiado</MenuItem>
                          <MenuItem value="cancelled">Cancelado</MenuItem>
                        </Select>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {/* Dialog for Score Editing */}
          <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)}>
            <DialogTitle sx={{ fontFamily: 'Outfit', fontWeight: 'bold' }}>Definir Placar Oficinal</DialogTitle>
            <DialogContent>
              {editingMatch && (
                <Stack spacing={2} sx={{ mt: 1, minWidth: 350 }}>
                  <Typography variant="subtitle2" align="center" sx={{ fontWeight: 'bold' }}>
                    {editingMatch.team1_name} vs {editingMatch.team2_name}
                  </Typography>
                  <Divider />
                  
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>Placar Tempo Normal + Prorrogação (120 mins):</Typography>
                  <Stack direction="row" spacing={2} justifyContent="center" alignItems="center">
                    <TextField label={editingMatch.team1_name} size="small" type="number" value={goals1} onChange={(e) => setGoals1(e.target.value)} />
                    <Typography>x</Typography>
                    <TextField label={editingMatch.team2_name} size="small" type="number" value={goals2} onChange={(e) => setGoals2(e.target.value)} />
                  </Stack>

                  <Typography variant="body2" sx={{ fontWeight: 600, mt: 1 }}>Placar Prorrogação (Total se houver):</Typography>
                  <Stack direction="row" spacing={2} justifyContent="center" alignItems="center">
                    <TextField label="Gols Mandante" size="small" type="number" value={etGoals1} onChange={(e) => setEtGoals1(e.target.value)} placeholder="vazio" />
                    <Typography>x</Typography>
                    <TextField label="Gols Visitante" size="small" type="number" value={etGoals2} onChange={(e) => setEtGoals2(e.target.value)} placeholder="vazio" />
                  </Stack>

                  <Typography variant="body2" sx={{ fontWeight: 600, mt: 1 }}>Decisão por Pênaltis (Disputa se houver):</Typography>
                  <Stack direction="row" spacing={2} justifyContent="center" alignItems="center">
                    <TextField label="Pênaltis Mandante" size="small" type="number" value={penGoals1} onChange={(e) => setPenGoals1(e.target.value)} placeholder="vazio" />
                    <Typography>x</Typography>
                    <TextField label="Pênaltis Visitante" size="small" type="number" value={penGoals2} onChange={(e) => setPenGoals2(e.target.value)} placeholder="vazio" />
                  </Stack>
                </Stack>
              )}
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setDialogOpen(false)}>Cancelar</Button>
              <Button onClick={handleSaveScore} variant="contained" color="primary">Salvar Placar</Button>
            </DialogActions>
          </Dialog>
        </Stack>
      )}

      {/* ==========================================
          TAB 1: INTEGRATION / SYNC
         ========================================== */}
      {tabIndex === 1 && (
        <Stack spacing={4}>
          <Card>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2 }}>
                🔄 Controle da Sincronização Automática
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                A sincronização automática roda diariamente às 01:00 AM consultando os repositórios do openfootball. Abaixo, você pode forçar as operações manualmente.
              </Typography>
              <Stack direction="row" spacing={2}>
                <Button variant="contained" color="secondary" startIcon={<SyncIcon />} onClick={handleTriggerInitialSeed} disabled={syncLoading}>
                  Seed Carga Inicial (Times/Estádios/Tabela)
                </Button>
                <Button variant="contained" color="primary" startIcon={<SyncIcon />} onClick={handleTriggerSyncJob} disabled={syncLoading}>
                  Executar Varredura e Sync de Resultados
                </Button>
              </Stack>
            </CardContent>
          </Card>

          {/* Diffs Pending Review Panel */}
          <Card>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                ⌛ Diffs de Placares Pendentes de Revisão ({syncDiffs.length})
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Se um resultado oficial for alterado na sincronização após ter sido confirmado por um administrador, o sistema NÃO sobrescreve silenciosamente. A alteração fica listada aqui para aprovação manual.
              </Typography>
              
              <TableContainer component={Paper} sx={{ boxShadow: 'none' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Partida ID</TableCell>
                      <TableCell>Valor Atual (Confirmado)</TableCell>
                      <TableCell>Novo Valor (Sincronizado)</TableCell>
                      <TableCell align="center">Ações</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {syncDiffs.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                          Nenhuma divergência de placar pendente de revisão.
                        </TableCell>
                      </TableRow>
                    ) : (
                      syncDiffs.map(diff => (
                        <TableRow key={diff.id}>
                          <TableCell>
                            <strong>#{diff.match_id}</strong>
                          </TableCell>
                          <TableCell>
                            Placar: {diff.previous_value.score_ft_team1} x {diff.previous_value.score_ft_team2} ({diff.previous_value.status})
                          </TableCell>
                          <TableCell sx={{ color: 'warning.main', fontWeight: 'bold' }}>
                            Placar: {diff.new_value.score_ft_team1} x {diff.new_value.score_ft_team2} ({diff.new_value.status})
                          </TableCell>
                          <TableCell align="center">
                            <Stack direction="row" spacing={1} justifyContent="center">
                              <IconButton color="success" onClick={() => handleApplyDiff(diff.id)}>
                                <CheckIcon />
                              </IconButton>
                              <IconButton color="error" onClick={() => handleRejectDiff(diff.id)}>
                                <CloseIcon />
                              </IconButton>
                            </Stack>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>

          {/* Raw Log Output console */}
          {syncResult && (
            <Card sx={{ bgcolor: '#111827' }}>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="caption" sx={{ display: 'block', color: 'secondary.main', mb: 1, fontWeight: 'bold' }}>
                  Log de Retorno da Sincronização:
                </Typography>
                <Box component="pre" sx={{ fontSize: '0.8rem', color: '#34d399', overflowX: 'auto', m: 0 }}>
                  {syncResult}
                </Box>
              </CardContent>
            </Card>
          )}
        </Stack>
      )}

      {/* ==========================================
          TAB 2: SCORING MULTIPLIERS (System Admin Only)
         ========================================== */}
      {tabIndex === 2 && user?.role === 'system_admin' && (
        <Stack spacing={4}>
          <Grid container spacing={3}>
            {/* Multiplier Form & Settings */}
            <Grid item xs={12} md={6}>
              <Card sx={{ height: '100%' }}>
                <CardContent sx={{ p: 4 }}>
                  <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                    🎛️ Alterar Multiplicador de Fase
                  </Typography>
                  
                  <Box component="form" onSubmit={handleUpdateMultiplier}>
                    <Stack spacing={3}>
                      <FormControl size="small" fullWidth required>
                        <InputLabel>Fase do Torneio</InputLabel>
                        <Select
                          value={selectedMultStage}
                          label="Fase do Torneio"
                          onChange={(e) => {
                            setSelectedMultStage(e.target.value)
                            const current = multipliers.find(m => m.stage === e.target.value)
                            setNewMultValue(current ? current.multiplier : '')
                          }}
                        >
                          {multipliers.map(m => (
                            <MenuItem key={m.stage} value={m.stage}>
                              {m.stage === 'Group Stage' ? 'Fase de Grupos' : m.stage}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                      
                      <TextField
                        label="Novo Multiplicador"
                        type="number"
                        inputProps={{ step: 0.1, min: 0.1 }}
                        size="small"
                        required
                        fullWidth
                        value={newMultValue}
                        onChange={(e) => setNewMultValue(e.target.value)}
                        placeholder="Ex: 2.5"
                      />

                      <TextField
                        label="Comentário/Motivo"
                        variant="outlined"
                        size="small"
                        fullWidth
                        multiline
                        rows={2}
                        value={multReason}
                        onChange={(e) => setMultReason(e.target.value)}
                        placeholder="Motivo da alteração nas regras..."
                      />

                      <Button type="submit" variant="contained" color="primary" startIcon={<SaveIcon />}>
                        Salvar e Recalcular Rankings
                      </Button>
                    </Stack>
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            {/* Current Multipliers Table */}
            <Grid item xs={12} md={6}>
              <Card sx={{ height: '100%' }}>
                <CardContent sx={{ p: 4 }}>
                  <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                    📊 Multiplicadores Atuais
                  </Typography>
                  <TableContainer component={Paper} sx={{ boxShadow: 'none' }}>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Fase</TableCell>
                          <TableCell align="center">Multiplicador</TableCell>
                          <TableCell align="center">Última Atualização</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {multipliers.map(m => (
                          <TableRow key={m.stage}>
                            <TableCell sx={{ fontWeight: 600 }}>
                              {m.stage === 'Group Stage' ? 'Fase de Grupos' : m.stage}
                            </TableCell>
                            <TableCell align="center" sx={{ color: 'primary.light', fontWeight: 800 }}>
                              {m.multiplier}x
                            </TableCell>
                            <TableCell align="center">
                              {formatDateTime(m.updated_at)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                  
                  <Box sx={{ mt: 3 }}>
                    <Button variant="outlined" color="error" fullWidth onClick={handleForceRecalculateAll}>
                      Forçar Recálculo Geral Manual de Apostas
                    </Button>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* Audit History of Multipliers */}
          <Card>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                📜 Histórico de Alterações de Multiplicador
              </Typography>
              <TableContainer component={Paper} sx={{ boxShadow: 'none' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Data/Hora</TableCell>
                      <TableCell>Fase</TableCell>
                      <TableCell align="center">Anterior</TableCell>
                      <TableCell align="center">Novo</TableCell>
                      <TableCell>Alterado Por</TableCell>
                      <TableCell>Motivo</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {multHistory.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                          Nenhuma alteração registrada.
                        </TableCell>
                      </TableRow>
                    ) : (
                      multHistory.map(h => (
                        <TableRow key={h.id}>
                          <TableCell>{formatDateTime(h.timestamp)}</TableCell>
                          <TableCell><strong>{h.stage === 'Group Stage' ? 'Fase de Grupos' : h.stage}</strong></TableCell>
                          <TableCell align="center">{h.old_multiplier}x</TableCell>
                          <TableCell align="center" sx={{ color: 'primary.light', fontWeight: 700 }}>{h.new_multiplier}x</TableCell>
                          <TableCell>Admin</TableCell>
                          <TableCell>{h.reason || '-'}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Stack>
      )}

      {/* ==========================================
          TAB 3: PUBLISH ANNOUNCEMENTS (System Admin Only)
         ========================================== */}
      {tabIndex === 3 && user?.role === 'system_admin' && (
        <Card sx={{ maxWidth: 650, mx: 'auto' }}>
          <CardContent sx={{ p: 4 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
              📢 Publicar Comunicado Oficial
            </Typography>
            <Divider sx={{ mb: 3 }} />

            <Box component="form" onSubmit={handleCreateAnnouncement}>
              <Stack spacing={3}>
                <TextField
                  label="Título do Comunicado"
                  variant="outlined"
                  required
                  fullWidth
                  value={annTitle}
                  onChange={(e) => setAnnTitle(e.target.value)}
                  placeholder="Ex: Prorrogação adiciona gols ao palpite oficial!"
                />
                
                <TextField
                  label="Texto da Mensagem"
                  variant="outlined"
                  required
                  fullWidth
                  multiline
                  rows={4}
                  value={annBody}
                  onChange={(e) => setAnnBody(e.target.value)}
                  placeholder="Escreva os detalhes do aviso..."
                />

                <Grid container spacing={2}>
                  {/* Priority selector */}
                  <Grid item xs={6}>
                    <FormControl size="small" fullWidth>
                      <InputLabel>Prioridade</InputLabel>
                      <Select value={annPriority} label="Prioridade" onChange={(e) => setAnnPriority(e.target.value)}>
                        <MenuItem value="low">Baixa</MenuItem>
                        <MenuItem value="medium">Média (Aviso)</MenuItem>
                        <MenuItem value="high">Alta (Urgente)</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>

                  {/* Target Audience Selector */}
                  <Grid item xs={6}>
                    <FormControl size="small" fullWidth>
                      <InputLabel>Público Alvo</InputLabel>
                      <Select value={annTarget} label="Público Alvo" onChange={(e) => setAnnTarget(e.target.value)}>
                        <MenuItem value="global">Todos os Participantes</MenuItem>
                        <MenuItem value="group">Grupo Específico</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                </Grid>

                {/* Target group select */}
                {annTarget === 'group' && (
                  <FormControl size="small" fullWidth required>
                    <InputLabel>Selecionar Grupo Alvo</InputLabel>
                    <Select value={annTargetGroup} label="Selecionar Grupo Alvo" onChange={(e) => setAnnTargetGroup(e.target.value)}>
                      {groups.map(g => (
                        <MenuItem key={g.id} value={g.id}>{g.name}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                )}

                <Button type="submit" variant="contained" color="primary" size="large">
                  Publicar Comunicado
                </Button>
              </Stack>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* ==========================================
          TAB 4: USERS / RBAC OVERRIDES (System Admin Only)
         ========================================== */}
      {tabIndex === 4 && user?.role === 'system_admin' && (
        <Stack spacing={3}>
          <Card>
            <CardContent sx={{ p: 2 }}>
              <TextField
                label="Buscar usuários por username, nome ou e-mail..."
                variant="outlined"
                size="small"
                fullWidth
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
              />
            </CardContent>
          </Card>

          <TableContainer component={Paper} sx={{ borderRadius: 3 }}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Participante</TableCell>
                  <TableCell>E-mail</TableCell>
                  <TableCell align="center">Função Administrativa</TableCell>
                  <TableCell align="center">Acesso Ativo</TableCell>
                  <TableCell align="center">Data Registro</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredUsers.map(u => (
                  <TableRow key={u.id}>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>{u.display_name}</Typography>
                      <Typography variant="caption" color="text.secondary">@{u.username}</Typography>
                    </TableCell>
                    <TableCell>{u.email}</TableCell>
                    <TableCell align="center">
                      <Select
                        size="small"
                        value={u.role}
                        disabled={u.id === user.id}
                        onChange={(e) => handleChangeUserRole(u.id, e.target.value)}
                        sx={{ fontSize: '0.85rem' }}
                      >
                        <MenuItem value="participant">Participante</MenuItem>
                        <MenuItem value="group_admin">Admin Grupo</MenuItem>
                        <MenuItem value="score_admin">Admin Resultados</MenuItem>
                        <MenuItem value="system_admin">Admin Geral</MenuItem>
                      </Select>
                    </TableCell>
                    <TableCell align="center">
                      <Switch
                        checked={u.is_active}
                        disabled={u.id === user.id}
                        color="success"
                        onChange={() => handleToggleUserActive(u.id, u.is_active)}
                      />
                    </TableCell>
                    <TableCell align="center">
                      {new Date(u.created_at).toLocaleDateString('pt-BR')}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      )}

      {/* ==========================================
          TAB 5: AUDIT LOGS & CSV EXPORTS (System Admin Only)
         ========================================== */}
      {tabIndex === 5 && user?.role === 'system_admin' && (
        <Stack spacing={4}>
          {/* CSV Exports Control */}
          <Card>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                📥 Exportar Dados para Planilhas (CSV)
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={4}>
                  <Button variant="outlined" startIcon={<DownloadIcon />} onClick={() => handleExportCSV('users')} fullWidth>
                    Exportar Usuários
                  </Button>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Button variant="outlined" startIcon={<DownloadIcon />} onClick={() => handleExportCSV('predictions')} fullWidth>
                    Exportar Todos os Palpites
                  </Button>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Button variant="outlined" startIcon={<DownloadIcon />} onClick={() => handleExportCSV('scores')} fullWidth>
                    Exportar Resultados Oficiais
                  </Button>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Button variant="outlined" startIcon={<DownloadIcon />} onClick={() => handleExportCSV('ranking')} fullWidth>
                    Exportar Classificação Geral
                  </Button>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Button variant="outlined" startIcon={<DownloadIcon />} onClick={() => handleExportCSV('audit-logs')} fullWidth>
                    Exportar Logs de Auditoria
                  </Button>
                </Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* Audit Logs List */}
          <Card>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                🕵️ Rastro de Auditoria e Segurança
              </Typography>
              
              <TableContainer component={Paper} sx={{ maxHeight: 500, boxShadow: 'none' }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell>Data/Hora</TableCell>
                      <TableCell>Ação</TableCell>
                      <TableCell>Alvo</TableCell>
                      <TableCell>ID Alvo</TableCell>
                      <TableCell>Observação / Origem</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {auditLogs.map(log => (
                      <TableRow key={log.id}>
                        <TableCell sx={{ fontSize: '0.8rem' }}>{formatDateTime(log.timestamp)}</TableCell>
                        <TableCell>
                          <Chip label={log.action} size="small" variant="outlined" color="primary" />
                        </TableCell>
                        <TableCell>{log.target_type}</TableCell>
                        <TableCell sx={{ fontSize: '0.8rem', fontFamily: 'monospace' }}>{log.target_id || '-'}</TableCell>
                        <TableCell sx={{ fontSize: '0.8rem' }}>{log.reason || '-'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Stack>
      )}

      {/* ==========================================
          TAB 6: PAYMENTS / PIX CONFIGURATION
         ========================================== */}
      {tabIndex === 6 && (
        <Grid container spacing={3}>
          {/* Pix Config Form */}
          <Grid item xs={12} md={4}>
            <Card>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" gutterBottom sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2 }}>
                  ⚙️ Configuração Geral do Pix
                </Typography>
                <Divider sx={{ mb: 3 }} />
                <Box component="form" onSubmit={handleSavePixConfig}>
                  <Stack spacing={2.5}>
                    <TextField
                      label="Chave Pix do Bolão"
                      variant="outlined"
                      fullWidth
                      required
                      value={pixKey}
                      onChange={(e) => setPixKey(e.target.value)}
                      placeholder="E-mail, Telefone, CPF ou Chave Aleatória"
                    />
                    <TextField
                      label="Nome do Beneficiário"
                      variant="outlined"
                      fullWidth
                      required
                      value={pixName}
                      onChange={(e) => setPixName(e.target.value)}
                      placeholder="Nome impresso no Pix"
                      helperText="Ex: JOAO SILVA"
                    />
                    <TextField
                      label="Cidade do Beneficiário"
                      variant="outlined"
                      fullWidth
                      required
                      value={pixCity}
                      onChange={(e) => setPixCity(e.target.value)}
                      placeholder="Cidade sem acentos"
                      helperText="Ex: SAO PAULO"
                    />
                    <TextField
                      label="Valor da Taxa de Inscrição (R$)"
                      variant="outlined"
                      type="number"
                      inputProps={{ step: "0.01", min: "0" }}
                      fullWidth
                      required
                      value={pixEntryFee}
                      onChange={(e) => setPixEntryFee(e.target.value)}
                      placeholder="Ex: 50.00"
                    />
                    <Button
                      type="submit"
                      variant="contained"
                      color="primary"
                      startIcon={<SaveIcon />}
                      sx={{ mt: 1, borderRadius: 2 }}
                    >
                      Salvar Configurações
                    </Button>
                  </Stack>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          {/* User Payments Submissions Table */}
          <Grid item xs={12} md={8}>
            <TableContainer component={Paper} sx={{ borderRadius: 3 }}>
              <Box sx={{ p: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit' }}>
                  👥 Comprovantes de Inscrição
                </Typography>
                <Chip 
                  label={`${paymentUsers.filter(u => u.payment_status === 'submitted').length} pendente(s)`} 
                  color="warning" 
                  size="small" 
                  sx={{ fontWeight: 'bold' }} 
                />
              </Box>
              <Divider />
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Usuário / Nome</TableCell>
                    <TableCell>Chave Pix Informada</TableCell>
                    <TableCell align="center">Status</TableCell>
                    <TableCell align="center">Comprovante</TableCell>
                    <TableCell align="center">Ações</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {paymentUsers.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                        Nenhum usuário cadastrado no sistema.
                      </TableCell>
                    </TableRow>
                  ) : (
                    paymentUsers.map(u => (
                      <TableRow key={u.id}>
                        <TableCell>
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>{u.display_name}</Typography>
                          <Typography variant="caption" color="text.secondary">@{u.username}</Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2">{u.pix_key_receive || '-'}</Typography>
                        </TableCell>
                        <TableCell align="center">
                          {u.payment_status === 'approved' && <Chip label="Aprovado" color="success" size="small" />}
                          {u.payment_status === 'submitted' && <Chip label="Aguardando" color="warning" size="small" />}
                          {u.payment_status === 'rejected' && <Chip label="Recusado" color="error" size="small" />}
                          {u.payment_status === 'pending' && <Chip label="Pendente" variant="outlined" size="small" />}
                        </TableCell>
                        <TableCell align="center">
                          {u.payment_proof_filename ? (
                            <Link href={`${axios.defaults.baseURL || ''}/api/payments/proof/${u.id}`} target="_blank" rel="noopener" sx={{ fontSize: '0.85rem' }}>
                              Ver Comprovante
                            </Link>
                          ) : (
                            <Typography variant="caption" color="text.secondary">Não enviado</Typography>
                          )}
                        </TableCell>
                        <TableCell align="center">
                          <Stack direction="row" spacing={1} justifyContent="center">
                            <Button
                              size="small"
                              variant="contained"
                              color="success"
                              disabled={u.payment_status === 'approved'}
                              onClick={() => handleApprovePayment(u.id)}
                            >
                              Aprovar
                            </Button>
                            <Button
                              size="small"
                              variant="outlined"
                              color="error"
                              disabled={u.payment_status === 'rejected' || !u.payment_proof_filename}
                              onClick={() => handleOpenRejectDialog(u.id)}
                            >
                              Recusar
                            </Button>
                          </Stack>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </Grid>
        </Grid>
      )}

      {tabIndex === 7 && user?.role === 'system_admin' && (
        <Stack spacing={3}>
          <Card>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                ✉️ Enviar Novo Convite de Cadastro
              </Typography>
              <Box component="form" onSubmit={handleSendInvitation} sx={{ display: 'flex', gap: 2, alignItems: 'center', maxWidth: 600 }}>
                <TextField
                  label="E-mail do Convidado"
                  variant="outlined"
                  type="email"
                  required
                  fullWidth
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="ex: convidado@email.com"
                />
                <Button
                  type="submit"
                  variant="contained"
                  color="primary"
                  disabled={inviting}
                  sx={{ py: 1.5, px: 4, fontWeight: 'bold', whiteSpace: 'nowrap' }}
                >
                  {inviting ? 'Enviando...' : 'Enviar Convite'}
                </Button>
              </Box>
            </CardContent>
          </Card>

          <Card>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                Convites Gerados
              </Typography>
              
              {invitationsList.length === 0 ? (
                <Alert severity="info" sx={{ borderRadius: 2 }}>Nenhum convite enviado ainda.</Alert>
              ) : (
                <TableContainer component={Paper} sx={{ borderRadius: 3, border: '1px solid #1f2937' }}>
                  <Table>
                    <TableHead sx={{ bgcolor: 'rgba(255,255,255,0.02)' }}>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold' }}>E-mail</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>Código</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>Status</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>Criado em</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>Usado em</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {invitationsList.map((inv) => (
                        <TableRow key={inv.id} hover>
                          <TableCell>{inv.email}</TableCell>
                          <TableCell sx={{ fontFamily: 'monospace', fontWeight: 600 }}>{inv.code}</TableCell>
                          <TableCell>
                            {inv.is_used ? (
                              <Chip label="Usado" color="success" size="small" sx={{ fontWeight: 600 }} />
                            ) : (
                              <Chip label="Pendente" color="warning" size="small" sx={{ fontWeight: 600 }} />
                            )}
                          </TableCell>
                          <TableCell>{new Date(inv.created_at).toLocaleString()}</TableCell>
                          <TableCell>{inv.used_at ? new Date(inv.used_at).toLocaleString() : '-'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </CardContent>
          </Card>
        </Stack>
      )}

      {/* Dialog for Payment Rejection Justification */}
      <Dialog open={rejectDialogOpen} onClose={() => setRejectDialogOpen(false)}>
        <DialogTitle sx={{ fontFamily: 'Outfit', fontWeight: 'bold' }}>Justificativa para Recusa de Pagamento</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1, minWidth: 350 }}>
            <Typography variant="body2" color="text.secondary">
              Escreva o motivo pelo qual este comprovante está sendo recusado. Isso será mostrado para o usuário.
            </Typography>
            <TextField
              label="Justificativa da Recusa"
              multiline
              rows={3}
              variant="outlined"
              fullWidth
              required
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              placeholder="Ex: Comprovante de outro bolão ou valor incompleto."
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRejectDialogOpen(false)}>Cancelar</Button>
          <Button onClick={handleConfirmRejectPayment} variant="contained" color="error">Recusar Pagamento</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
