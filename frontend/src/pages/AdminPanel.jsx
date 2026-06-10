import React, { useState, useEffect } from 'react'
import {
  Box, Card, CardContent, Typography, Tabs, Tab, Grid, TextField, Button,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  MenuItem, Select, FormControl, InputLabel, Switch, Checkbox, FormControlLabel, Alert, Snackbar, Stack,
  Divider, Accordion, AccordionSummary, AccordionDetails, Chip, Dialog, DialogTitle, DialogContent, DialogActions, Link, Badge,
  IconButton, Tooltip, Autocomplete, ToggleButton, ToggleButtonGroup
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
  Description as ProofIcon,
  HourglassEmpty as PendingPaymentIcon,
  Payments as PaymentIcon,
  Mail as MailIcon,
  Undo as RevertIcon,
  Refresh as RefreshIcon
} from '@mui/icons-material'
import axios from 'axios'
import { useAuth } from '../App'
import { useSearchParams } from 'react-router-dom'
import { getFlagUrl } from '../utils/flags'

const userNameCollator = new Intl.Collator('pt-BR', {
  sensitivity: 'base',
  numeric: true
})

const compareUsersByName = (a, b) => {
  const displayNameCompare = userNameCollator.compare(a.display_name || '', b.display_name || '')
  if (displayNameCompare !== 0) return displayNameCompare

  const usernameCompare = userNameCollator.compare(a.username || '', b.username || '')
  if (usernameCompare !== 0) return usernameCompare

  return userNameCollator.compare(a.email || '', b.email || '')
}

const getAllowedTabs = (role) => {
  const tabs = ['matches', 'sync']
  if (role === 'system_admin') {
    tabs.push('scoring', 'announcements', 'users', 'audit', 'payments', 'invitations')
  } else if (role === 'score_admin') {
    tabs.push('payments')
  }
  return tabs
}

export default function AdminPanel() {
  const { user } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  
  // Tabs: 0=Matches, 1=Sync, 2=Config, 3=Announcements, 4=Users, 5=Logs
  const [tabIndex, setTabIndex] = useState('matches')
  
  // Shared options
  const [matches, setMatches] = useState([])
  const [stages, setStages] = useState([])

  useEffect(() => {
    if (!user) return
    const requestedTab = searchParams.get('tab')
    const allowedTabs = getAllowedTabs(user.role)
    if (requestedTab && allowedTabs.includes(requestedTab)) {
      setTabIndex(requestedTab)
    } else if (!allowedTabs.includes(tabIndex)) {
      setTabIndex('matches')
    }
  }, [searchParams, user, tabIndex])

  const handleTabChange = (event, value) => {
    setTabIndex(value)
    if (value === 'payments') {
      setSearchParams({ tab: 'payments' })
    } else if (searchParams.has('tab')) {
      const nextParams = new URLSearchParams(searchParams)
      nextParams.delete('tab')
      setSearchParams(nextParams)
    }
  }
  
  // 0. Matches Management State
  const [filterStage, setFilterStage] = useState('All')
  const [scoreDrafts, setScoreDrafts] = useState({})
  const [savingScoreGroup, setSavingScoreGroup] = useState(null)

  // 1. Sync State
  const [syncDiffs, setSyncDiffs] = useState([])
  const [syncLoading, setSyncLoading] = useState(false)
  const [syncResult, setSyncResult] = useState('')
  const [footballDataLogs, setFootballDataLogs] = useState([])
  const [footballDataLogsLoading, setFootballDataLogsLoading] = useState(false)

  // 2. Multipliers State
  const [multipliers, setMultipliers] = useState([])
  const [multHistory, setMultHistory] = useState([])
  const [selectedMultStage, setSelectedMultStage] = useState('')
  const [newMultValue, setNewMultValue] = useState('')
  const [multReason, setMultReason] = useState('')
  const [predictionLockHours, setPredictionLockHours] = useState('3')
  const [predictionLockMaxHours, setPredictionLockMaxHours] = useState(168)

  // 3. Announcements State
  const [annTitle, setAnnTitle] = useState('')
  const [annBody, setAnnBody] = useState('')
  const [annPriority, setAnnPriority] = useState('low')
  const [annTarget, setAnnTarget] = useState('global')
  const [annTargetGroup, setAnnTargetGroup] = useState('')
  const [groups, setGroups] = useState([])
  const [chargeTemplate, setChargeTemplate] = useState('')
  const [placeholderValues, setPlaceholderValues] = useState({})
  const [savingTemplate, setSavingTemplate] = useState(false)
  const [approvalTemplate, setApprovalTemplate] = useState('')
  const [approvalValues, setApprovalValues] = useState({})
  const [savingApprovalTemplate, setSavingApprovalTemplate] = useState(false)

  // 4. Users State
  const [usersList, setUsersList] = useState([])
  const [userSearch, setUserSearch] = useState('')
  const [hideActiveUsers, setHideActiveUsers] = useState(true)
  const [deleteUserTarget, setDeleteUserTarget] = useState(null)
  const [deleteUserDialogOpen, setDeleteUserDialogOpen] = useState(false)

  // 5. Audit Logs State
  const [auditLogs, setAuditLogs] = useState([])

  // 6. Payments State
  const [pixKey, setPixKey] = useState('')
  const [pixName, setPixName] = useState('')
  const [pixCity, setPixCity] = useState('')
  const [pixEntryFee, setPixEntryFee] = useState('')
  const [paymentUsers, setPaymentUsers] = useState([])
  const [hideApprovedPayments, setHideApprovedPayments] = useState(true)
  const [chargingDebtors, setChargingDebtors] = useState(false)
  const [revertPaymentTarget, setRevertPaymentTarget] = useState(null)

  const [confirmDialog, setConfirmDialog] = useState({
    open: false,
    title: '',
    message: '',
    onConfirm: null
  })

  const showConfirm = (title, message, onConfirm) => {
    setConfirmDialog({
      open: true,
      title,
      message,
      onConfirm: () => {
        onConfirm()
        setConfirmDialog(prev => ({ ...prev, open: false }))
      }
    })
  }

  // Invitations State
  const [inviteEmail, setInviteEmail] = useState('')
  const [invitationsList, setInvitationsList] = useState([])
  const [inviting, setInviting] = useState(false)
  const [hiddenRegistrationLink, setHiddenRegistrationLink] = useState(null)

  // UI status
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(true)

  // 8. Knockout Setup State
  const [matchMode, setMatchMode] = useState('scores') // 'scores' or 'knockout'
  const [knockoutSetup, setKnockoutSetup] = useState(null)
  const [knockoutLoading, setKnockoutLoading] = useState(false)
  const [syncFixturesLoading, setSyncFixturesLoading] = useState(false)
  const [knockoutForm, setKnockoutForm] = useState({})
  const [definingTeamsMatchId, setDefiningTeamsMatchId] = useState(null)
  const [selectedRefGroup, setSelectedRefGroup] = useState('Grupo A')

  const fetchKnockoutSetup = async () => {
    setKnockoutLoading(true)
    setError('')
    try {
      const res = await axios.get('/api/admin/matches/knockout-setup')
      setKnockoutSetup(res.data)
      
      const initialForm = {}
      res.data.matches.forEach(m => {
        initialForm[m.id] = {
          team1_name: m.team1_name,
          team2_name: m.team2_name
        }
      })
      setKnockoutForm(initialForm)
      
      const groupNames = Object.keys(res.data.groups).sort()
      if (groupNames.length > 0 && !groupNames.includes(selectedRefGroup) && selectedRefGroup !== 'third_placed') {
        setSelectedRefGroup(groupNames[0])
      }
    } catch (err) {
      console.error(err)
      setError(err.response?.data?.detail || 'Erro ao carregar setup do mata-mata.')
    } finally {
      setKnockoutLoading(false)
    }
  }

  const handleSaveKnockoutMatch = async (matchId) => {
    const form = knockoutForm[matchId]
    if (!form || !form.team1_name || !form.team2_name) {
      setError('Por favor, selecione ambos os times.')
      return
    }
    
    setDefiningTeamsMatchId(matchId)
    setError('')
    setSuccess('')
    try {
      const res = await axios.post(`/api/admin/matches/${matchId}/define-teams`, {
        team1_name: form.team1_name,
        team2_name: form.team2_name
      })
      showSuccess(res.data.message || 'Times definidos com sucesso!')
      await fetchKnockoutSetup()
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao definir os times da partida.')
    } finally {
      setDefiningTeamsMatchId(null)
    }
  }

  const handleTriggerFootballDataFixturesSync = async () => {
    setSyncFixturesLoading(true)
    setError('')
    setSuccess('')
    try {
      const res = await axios.post('/api/admin/football-data/sync-fixtures')
      if (res.data.updated_matches > 0) {
        showSuccess(`Sincronização concluída! ${res.data.updated_matches} confronto(s) atualizado(s).`)
        await fetchKnockoutSetup()
      } else {
        showSuccess('Sincronização concluída! Nenhum novo confronto atualizado.')
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao rodar sincronização de confrontos.')
    } finally {
      setSyncFixturesLoading(false)
    }
  }

  const handleApplySuggestions = (matchId, sug1, sug2) => {
    if (!sug1 || !sug2) return
    setKnockoutForm(prev => ({
      ...prev,
      [matchId]: {
        team1_name: sug1,
        team2_name: sug2
      }
    }))
  }

  const handleApplyAllSuggestions = () => {
    if (!knockoutSetup) return
    const nextForm = { ...knockoutForm }
    let count = 0
    knockoutSetup.matches.forEach(m => {
      if (m.suggested_team1 && m.suggested_team2 && (m.team1_is_placeholder || m.team2_is_placeholder)) {
        nextForm[m.id] = {
          team1_name: m.suggested_team1,
          team2_name: m.suggested_team2
        }
        count++
      }
    })
    setKnockoutForm(nextForm)
    showSuccess(`Sugestões aplicadas ao rascunho de ${count} confronto(s).`)
  }

  useEffect(() => {
    if (tabIndex === 'matches' && matchMode === 'knockout') {
      fetchKnockoutSetup()
    }
  }, [tabIndex, matchMode])

  const loadFootballDataLogs = async ({ silent = false } = {}) => {
    try {
      if (!silent) setFootballDataLogsLoading(true)
      const res = await axios.get('/api/admin/football-data/logs?limit=20')
      setFootballDataLogs(res.data)
    } catch (err) {
      if (!silent) setError('Erro ao carregar logs do football-data.')
    } finally {
      if (!silent) setFootballDataLogsLoading(false)
    }
  }

  const loadInitialData = async () => {
    try {
      setLoading(true)
      setError('')
      
      // Load matches
      const matchesRes = await axios.get('/api/matches?missing_score=true&limit=5')
      setMatches(matchesRes.data)
      setScoreDrafts(createScoreDrafts(matchesRes.data))
      setStages(['All', ...new Set(matchesRes.data.map(m => m.stage))])

      // Depending on permissions and active tab, fetch other data
      if (user?.role === 'system_admin') {
        // Load multipliers
        const multRes = await axios.get('/api/admin/multipliers')
        setMultipliers(multRes.data)
        
        // Load multiplier history
        const histRes = await axios.get('/api/admin/multipliers/history')
        setMultHistory(histRes.data)

        // Load prediction lock setting
        const lockRes = await axios.get('/api/admin/settings/prediction-lock-hours')
        setPredictionLockHours(String(lockRes.data.hours))
        setPredictionLockMaxHours(lockRes.data.max_hours || 168)

        // Load groups (for announcement targets)
        const groupsRes = await axios.get('/api/groups')
        setGroups(groupsRes.data)

        // Load users list
        const usersRes = await axios.get('/api/admin/users')
        setUsersList([...usersRes.data].sort(compareUsersByName))

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
        setPaymentUsers([...paymentsRes.data].sort(compareUsersByName))

        // Load invitations list
        const invitesRes = await axios.get('/api/admin/invitations')
        setInvitationsList(invitesRes.data)

        // Load hidden registration link
        const regLinkRes = await axios.get('/api/admin/registration-link')
        setHiddenRegistrationLink(regLinkRes.data)
      } else if (user?.role === 'score_admin') {
        const paymentsRes = await axios.get('/api/payments/admin/list')
        setPaymentUsers([...paymentsRes.data].sort(compareUsersByName))
      }
      
      // Load pending sync diffs
      const diffsRes = await axios.get('/api/admin/sync/diffs')
      setSyncDiffs(diffsRes.data)
      await loadFootballDataLogs({ silent: true })
      
    } catch (err) {
      setError('Erro ao carregar dados do painel administrativo.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadInitialData()
  }, [])

  useEffect(() => {
    if (tabIndex !== 'sync') return undefined
    loadFootballDataLogs({ silent: true })
    const intervalId = setInterval(() => {
      loadFootballDataLogs({ silent: true })
    }, 5000)
    return () => clearInterval(intervalId)
  }, [tabIndex])

  // Save success message alert
  const showSuccess = (msg) => {
    setSuccess(msg)
    setTimeout(() => setSuccess(''), 3000)
  }

  // ==========================================
  // 0. Matches Actions
  // ==========================================
  const createScoreDrafts = (matchesList) => {
    const drafts = {}
    matchesList.forEach(match => {
      drafts[match.id] = {
        score_ft_team1: match.score_ft_team1 ?? '',
        score_ft_team2: match.score_ft_team2 ?? '',
        score_et_team1: match.score_et_team1 ?? '',
        score_et_team2: match.score_et_team2 ?? '',
        score_pen_team1: match.score_pen_team1 ?? '',
        score_pen_team2: match.score_pen_team2 ?? ''
      }
    })
    return drafts
  }

  const getScoreDraft = (matchId) => scoreDrafts[matchId] || {
    score_ft_team1: '',
    score_ft_team2: '',
    score_et_team1: '',
    score_et_team2: '',
    score_pen_team1: '',
    score_pen_team2: ''
  }

  const handleScoreDraftChange = (matchId, field, value) => {
    if (value !== '' && !/^\d+$/.test(value)) return
    setScoreDrafts(prev => ({
      ...prev,
      [matchId]: {
        ...getScoreDraft(matchId),
        [field]: value
      }
    }))
  }

  const buildScoreUpdatePayload = (match, draft) => {
    const ft1 = draft.score_ft_team1
    const ft2 = draft.score_ft_team2
    const isGroupStage = match.stage === 'Group Stage'
    const et1 = isGroupStage ? '' : draft.score_et_team1
    const et2 = isGroupStage ? '' : draft.score_et_team2
    const pen1 = isGroupStage ? '' : draft.score_pen_team1
    const pen2 = isGroupStage ? '' : draft.score_pen_team2

    const hasAnyValue = [ft1, ft2, et1, et2, pen1, pen2].some(v => v !== '')
    if (!hasAnyValue) return null

    if (ft1 === '' || ft2 === '') {
      throw new Error(`Informe o placar do tempo normal para ${match.team1_name} x ${match.team2_name}.`)
    }
    if ((et1 === '') !== (et2 === '')) {
      throw new Error(`Preencha os dois campos de prorrogação para ${match.team1_name} x ${match.team2_name}, ou deixe ambos vazios.`)
    }
    if ((pen1 === '') !== (pen2 === '')) {
      throw new Error(`Preencha os dois campos de pênaltis para ${match.team1_name} x ${match.team2_name}, ou deixe ambos vazios.`)
    }

    return {
      match_id: match.id,
      score_ft_team1: Number(ft1),
      score_ft_team2: Number(ft2),
      score_et_team1: et1 !== '' ? Number(et1) : null,
      score_et_team2: et2 !== '' ? Number(et2) : null,
      score_pen_team1: pen1 !== '' ? Number(pen1) : null,
      score_pen_team2: pen2 !== '' ? Number(pen2) : null
    }
  }

  const handleSaveScoreGroup = async (groupKey, groupMatches) => {
    try {
      const updates = groupMatches
        .map(match => buildScoreUpdatePayload(match, getScoreDraft(match.id)))
        .filter(Boolean)

      if (updates.length === 0) {
        alert('Informe pelo menos um placar para salvar este horário.')
        return
      }

      setSavingScoreGroup(groupKey)
      await axios.post('/api/admin/matches/score-batch', { scores: updates })
      showSuccess(`${updates.length} placar(es) salvo(s) como pendente(s) de revisão.`)
      loadInitialData()
    } catch (err) {
      alert(err.message || 'Erro ao salvar placares deste horário.')
    } finally {
      setSavingScoreGroup(null)
    }
  }

  const handleConfirmScore = (matchId) => {
    showConfirm(
      'Confirmar Resultado',
      'Confirmar este resultado? Os pontos serão fixados e esta pontuação não será sobrescrita pela sincronização automática.',
      async () => {
        try {
          await axios.post(`/api/admin/matches/${matchId}/confirm-score`)
          showSuccess('Placar confirmado pelo administrador com sucesso!')
          loadInitialData()
        } catch (err) {
          alert('Erro ao confirmar placar.')
        }
      }
    )
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
  const handleTriggerInitialSeed = () => {
    showConfirm(
      'Iniciar Seeding de Dados',
      'Iniciar o Seeding de Dados? Isso importará os times, estádios e tabela original do openfootball.',
      async () => {
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
    )
  }

  const handleTriggerSyncJob = async () => {
    setSyncLoading(true)
    setSyncResult('Consultando API oficial de resultados...')
    try {
      const res = await axios.post('/api/admin/football-data/check-scores')
      setSyncResult(JSON.stringify(res.data, null, 2))
      const updated = res.data?.updated_matches || 0
      showSuccess(updated > 0 ? `${updated} resultado(s) atualizado(s) pela API oficial.` : 'Consulta concluída. Nenhum resultado novo encontrado.')
      await loadFootballDataLogs({ silent: true })
      loadInitialData()
    } catch (err) {
      setSyncResult('Erro na consulta da API oficial: ' + (err.response?.data?.detail || err.message))
      await loadFootballDataLogs({ silent: true })
    } finally {
      setSyncLoading(false)
    }
  }

  const handleTriggerLegacyOpenfootballSync = async () => {
    setSyncLoading(true)
    setSyncResult('Executando sincronização legada com repositório openfootball...')
    try {
      const res = await axios.post('/api/admin/sync/job')
      setSyncResult(JSON.stringify(res.data, null, 2))
      showSuccess('Sincronização legada executada.')
      loadInitialData()
    } catch (err) {
      setSyncResult('Erro na sincronização legada: ' + err.message)
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
  const handleUpdateMultiplier = (e) => {
    e.preventDefault()
    if (!selectedMultStage || !newMultValue || isNaN(newMultValue) || parseFloat(newMultValue) <= 0) {
      alert('Por favor, informe uma fase válida e um multiplicador positivo.')
      return
    }

    showConfirm(
      'Atualizar Multiplicador',
      'ATENÇÃO: Mudar multiplicadores de fase forçará o recálculo de TODOS os palpites salvos e causará alterações instantâneas no ranking. Deseja prosseguir?',
      async () => {
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
    )
  }

  const handleForceRecalculateAll = () => {
    showConfirm(
      'Forçar Recálculo Total',
      'Forçar recálculo total? Isso irá reprocessar os pontos de cada palpite e classificar novamente o ranking.',
      async () => {
        try {
          await axios.post('/api/admin/recalculate-all')
          showSuccess('Recálculo de todas as apostas executado!')
        } catch (err) {
          alert('Erro ao forçar recálculo.')
        }
      }
    )
  }

  const handleUpdatePredictionLockHours = async (e) => {
    e.preventDefault()
    const hours = Number(predictionLockHours)
    if (!Number.isInteger(hours) || hours < 0 || hours > predictionLockMaxHours) {
      alert(`Informe um número inteiro de horas entre 0 e ${predictionLockMaxHours}.`)
      return
    }

    try {
      const res = await axios.put(`/api/admin/settings/prediction-lock-hours?hours=${hours}`)
      setPredictionLockHours(String(res.data.hours))
      setPredictionLockMaxHours(res.data.max_hours || predictionLockMaxHours)
      showSuccess('Janela de bloqueio dos palpites atualizada com sucesso!')
      loadInitialData()
    } catch (err) {
      alert(err.response?.data?.detail || 'Erro ao salvar a janela de bloqueio.')
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

  const loadChargeTemplate = async () => {
    try {
      const res = await axios.get('/api/payments/admin/charge-template')
      setChargeTemplate(res.data.template)
      setPlaceholderValues(res.data.values || {})
    } catch (err) {
      setError('Erro ao carregar o modelo de cobrança.')
    }
  }

  const compilePreview = (tmpl) => {
    if (!tmpl) return ''
    return tmpl
      .split('{{devedores}}').join(placeholderValues.devedores || '')
      .split('{{aprovados}}').join(String(placeholderValues.aprovados ?? 0))
      .split('{{aprovados_pagos}}').join(String(placeholderValues.aprovados_pagos ?? 0))
      .split('{{valor}}').join(placeholderValues.valor || 'R$ 0,00')
      .split('{{total_cadastrados}}').join(String(placeholderValues.total_cadastrados ?? 0))
      .split('{{devedores_qtd}}').join(String(placeholderValues.devedores_qtd ?? 0))
      .split('{{taxa_inscricao}}').join(placeholderValues.taxa_inscricao || 'R$ 0,00')
  }

  const handleSaveChargeTemplate = async (e) => {
    e.preventDefault()
    setSavingTemplate(true)
    setError('')
    setSuccess('')
    try {
      await axios.put('/api/payments/admin/charge-template', { template: chargeTemplate })
      showSuccess('Modelo de cobrança salvo com sucesso!')
    } catch (err) {
      setError('Erro ao salvar modelo de cobrança.')
    } finally {
      setSavingTemplate(false)
    }
  }

  const loadApprovalTemplate = async () => {
    try {
      const res = await axios.get('/api/payments/admin/approval-template')
      setApprovalTemplate(res.data.template)
      setApprovalValues(res.data.values || {})
    } catch (err) {
      setError('Erro ao carregar o modelo de aprovação de pagamento.')
    }
  }

  const compileApprovalPreview = (tmpl) => {
    if (!tmpl) return ''
    return tmpl
      .split('{{usuario}}').join(approvalValues.usuario || 'Fulano de Tal')
      .split('{{valor}}').join(approvalValues.valor || 'R$ 0,00')
      .split('{{prizepool}}').join(approvalValues.prizepool || '')
      .split('{{aprovados_pagos}}').join(String(approvalValues.aprovados_pagos ?? 0))
      .split('{{taxa_inscricao}}').join(approvalValues.taxa_inscricao || 'R$ 0,00')
  }

  const handleSaveApprovalTemplate = async (e) => {
    e.preventDefault()
    setSavingApprovalTemplate(true)
    setError('')
    setSuccess('')
    try {
      await axios.put('/api/payments/admin/approval-template', { template: approvalTemplate })
      showSuccess('Modelo de aprovação de pagamento salvo com sucesso!')
    } catch (err) {
      setError('Erro ao salvar modelo de aprovação de pagamento.')
    } finally {
      setSavingApprovalTemplate(false)
    }
  }

  useEffect(() => {
    if (tabIndex === 'announcements' && user) {
      loadChargeTemplate()
      loadApprovalTemplate()
    }
  }, [tabIndex, user])

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

  const handleOpenDeleteUserDialog = (targetUser) => {
    setDeleteUserTarget(targetUser)
    setDeleteUserDialogOpen(true)
  }

  const handleConfirmDeleteUser = async () => {
    if (!deleteUserTarget) return
    try {
      await axios.delete(`/api/admin/users/${deleteUserTarget.id}`)
      showSuccess(`Usuário ${deleteUserTarget.display_name} removido com sucesso.`)
      setDeleteUserDialogOpen(false)
      setDeleteUserTarget(null)
      loadInitialData()
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao remover usuário.')
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
    if (!isoString) return '-'
    const normalized = typeof isoString === 'string' && !/(z|[+-]\d{2}:?\d{2})$/i.test(isoString)
      ? `${isoString}Z`
      : isoString
    return new Date(normalized).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' })
  }

  const getFootballDataStatusColor = (status) => {
    if (status === 'success') return 'success'
    if (status === 'warning') return 'warning'
    if (status === 'error') return 'error'
    if (status === 'running') return 'info'
    return 'default'
  }

  const getFootballDataStatusLabel = (status) => {
    const labels = {
      running: 'Em execução',
      success: 'Concluído',
      warning: 'Atenção',
      error: 'Erro',
      skipped: 'Ignorado'
    }
    return labels[status] || status || 'Desconhecido'
  }

  const renderFootballDataEventExtra = (event) => {
    const extra = Object.fromEntries(
      Object.entries(event).filter(([key]) => !['timestamp', 'level', 'message'].includes(key))
    )
    if (Object.keys(extra).length === 0) return null
    return (
      <Box
        component="pre"
        sx={{
          mt: 1,
          p: 1.5,
          borderRadius: 1,
          bgcolor: '#020617',
          color: '#cbd5e1',
          fontSize: '0.72rem',
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          m: 0,
          marginTop: 1
        }}
      >
        {JSON.stringify(extra, null, 2)}
      </Box>
    )
  }

  const renderScoreInput = (matchId, field, value) => (
    <TextField
      size="small"
      type="number"
      value={value}
      onChange={(e) => handleScoreDraftChange(matchId, field, e.target.value)}
      inputProps={{ min: 0, step: 1, style: { textAlign: 'center', fontWeight: 700, fontSize: '1.05rem' } }}
      sx={{ width: { xs: 48, sm: 56 } }}
    />
  )

  const renderAdminTeamLabel = (match, teamNumber) => {
    const team = teamNumber === 1 ? match.team1 : match.team2
    const teamName = teamNumber === 1 ? match.team1_name : match.team2_name
    const flagUrl = getFlagUrl(team?.flag_icon, team)
    return (
      <Typography
        variant="body2"
        sx={{
          fontWeight: 700,
          minWidth: { xs: 78, sm: 140 },
          maxWidth: { xs: 92, sm: 180 },
          display: 'flex',
          alignItems: 'center',
          justifyContent: teamNumber === 1 ? 'flex-end' : 'flex-start',
          gap: 1,
          textAlign: teamNumber === 1 ? 'right' : 'left'
        }}
      >
        {teamNumber === 1 && flagUrl && <img src={flagUrl} alt="" style={{ width: 20, height: 14, borderRadius: 1.5, objectFit: 'cover' }} />}
        <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' }, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {teamName}
        </Box>
        <Box component="span" sx={{ display: { xs: 'inline', sm: 'none' }, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {team?.fifa_code || teamName}
        </Box>
        {teamNumber === 2 && flagUrl && <img src={flagUrl} alt="" style={{ width: 20, height: 14, borderRadius: 1.5, objectFit: 'cover' }} />}
      </Typography>
    )
  }

  const renderMatchStatusChip = (status) => {
    if (status === 'score_confirmed') return <Chip label="Confirmado" color="success" size="small" />
    if (status === 'score_pending_review') return <Chip label="Revisar" color="warning" size="small" />
    if (status === 'postponed') return <Chip label="Adiado" color="error" size="small" />
    if (status === 'cancelled') return <Chip label="Cancelado" color="error" size="small" />
    return <Chip label="Agendado" variant="outlined" size="small" />
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

  const handleConfirmRevertPaymentApproval = async () => {
    if (!revertPaymentTarget) return
    try {
      await axios.post(`/api/payments/admin/revert/${revertPaymentTarget.id}`)
      showSuccess('Aprovação de pagamento revertida.')
      setRevertPaymentTarget(null)
      loadInitialData()
    } catch (err) {
      alert(err.response?.data?.detail || 'Erro ao reverter aprovação de pagamento.')
    }
  }

  const handleChargeDebtors = async () => {
    try {
      setChargingDebtors(true)
      const response = await axios.post('/api/payments/admin/charge-debtors')
      showSuccess(`Cobrança enviada para ${response.data.debtors_count} participante(s).`)
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao enviar cobrança pelo WhatsApp.')
    } finally {
      setChargingDebtors(false)
    }
  }

  const handleViewPaymentProof = async (userId) => {
    const proofWindow = window.open('', '_blank', 'noopener')
    try {
      const response = await axios.get(`/api/payments/proof/${userId}`, {
        responseType: 'blob'
      })
      const url = window.URL.createObjectURL(response.data)
      if (proofWindow) {
        proofWindow.location = url
      } else {
        window.open(url, '_blank', 'noopener')
      }
      setTimeout(() => window.URL.revokeObjectURL(url), 60000)
    } catch (err) {
      if (proofWindow) proofWindow.close()
      setError(err.response?.data?.detail || 'Erro ao abrir comprovante.')
    }
  }

  const filteredMatches = matches.filter(m => {
    if (filterStage !== 'All' && m.stage !== filterStage) return false
    return true
  })

  const pendingPaymentApprovalsCount = paymentUsers.filter(u => u.payment_status === 'submitted').length
  const paymentDebtors = paymentUsers
    .filter(u => !['system_admin', 'score_admin'].includes(u.role) && u.payment_status !== 'approved')
    .sort(compareUsersByName)
  const visiblePaymentUsers = hideApprovedPayments
    ? paymentUsers.filter(u => u.payment_status !== 'approved').sort(compareUsersByName)
    : [...paymentUsers].sort(compareUsersByName)

  const groupedMatchesByKickoff = filteredMatches.reduce((groupsAcc, match) => {
    const key = match.kickoff_time
    if (!groupsAcc[key]) {
      groupsAcc[key] = {
        key,
        kickoff_time: match.kickoff_time,
        date: match.date,
        matches: []
      }
    }
    groupsAcc[key].matches.push(match)
    return groupsAcc
  }, {})

  const matchTimeGroups = Object.values(groupedMatchesByKickoff)
    .sort((a, b) => new Date(a.kickoff_time) - new Date(b.kickoff_time))
    .map(group => ({
      ...group,
      matches: group.matches.sort((a, b) => a.id - b.id)
    }))

  const totalUsersCount = usersList.length
  const activeUsersCount = usersList.filter(u => u.is_active).length
  const inactiveUsersCount = totalUsersCount - activeUsersCount
  const filteredUsers = usersList
    .filter(u => {
      if (hideActiveUsers && u.is_active) return false
      if (!userSearch.trim()) return true

      const s = userSearch.toLowerCase()
      return (
        u.username.toLowerCase().includes(s) ||
        u.display_name.toLowerCase().includes(s) ||
        u.email.toLowerCase().includes(s)
      )
    })
    .sort(compareUsersByName)

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

  const refreshInvitations = async () => {
    const res = await axios.get('/api/admin/invitations')
    setInvitationsList(res.data)
  }

  const handleResendInvitation = async (invitation) => {
    setError('')
    setSuccess('')
    try {
      await axios.post(`/api/admin/invitations/${invitation.id}/resend`)
      showSuccess(`Convite reenviado para ${invitation.email}.`)
      await refreshInvitations()
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao reenviar convite.')
    }
  }

  const handleDeleteInvitation = (invitation) => {
    showConfirm(
      'Excluir Convite',
      `Excluir o convite de ${invitation.email}?`,
      async () => {
        setError('')
        setSuccess('')
        try {
          await axios.delete(`/api/admin/invitations/${invitation.id}`)
          showSuccess(`Convite de ${invitation.email} excluído.`)
          await refreshInvitations()
        } catch (err) {
          setError(err.response?.data?.detail || 'Erro ao excluir convite.')
        }
      }
    )
  }

  const getHiddenRegistrationUrl = () => {
    if (!hiddenRegistrationLink?.path) return ''
    return `${window.location.origin}${hiddenRegistrationLink.path}`
  }

  const handleCopyHiddenRegistrationLink = async () => {
    const link = getHiddenRegistrationUrl()
    if (!link) return

    try {
      await navigator.clipboard.writeText(link)
      showSuccess('Link de cadastro copiado.')
    } catch (err) {
      setError('Não foi possível copiar o link automaticamente.')
    }
  }

  const handleRotateHiddenRegistrationLink = () => {
    showConfirm(
      'Gerar Novo Link Oculto',
      'Gerar um novo link oculto? O link atual deixará de funcionar.',
      async () => {
        setError('')
        setSuccess('')
        try {
          const res = await axios.post('/api/admin/registration-link/rotate')
          setHiddenRegistrationLink(res.data)
          showSuccess('Novo link oculto de cadastro gerado.')
        } catch (err) {
          setError(err.response?.data?.detail || 'Erro ao gerar novo link oculto.')
        }
      }
    )
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
        onChange={handleTabChange}
        textColor="primary"
        indicatorColor="primary"
        variant="scrollable"
        scrollButtons="auto"
        sx={{ borderBottom: 1, borderColor: 'divider', mb: 4 }}
      >
        <Tab value="matches" icon={<MatchIcon />} label="Placares & Jogos" iconPosition="start" sx={{ fontWeight: 'bold' }} />
        <Tab value="sync" icon={<SyncIcon />} label="Sincronização" iconPosition="start" sx={{ fontWeight: 'bold' }} />
        {user?.role === 'system_admin' && <Tab value="scoring" icon={<ConfigIcon />} label="Config. Pontuação" iconPosition="start" sx={{ fontWeight: 'bold' }} />}
        {user?.role === 'system_admin' && <Tab value="announcements" icon={<AnnIcon />} label="Publicar Comunicados" iconPosition="start" sx={{ fontWeight: 'bold' }} />}
        {user?.role === 'system_admin' && <Tab value="users" icon={<PeopleIcon />} label="Usuários & Acessos" iconPosition="start" sx={{ fontWeight: 'bold' }} />}
        {user?.role === 'system_admin' && <Tab value="audit" icon={<HistoryIcon />} label="Auditoria & Exportar" iconPosition="start" sx={{ fontWeight: 'bold' }} />}
        {(user?.role === 'system_admin' || user?.role === 'score_admin') && (
          <Tab
            value="payments"
            icon={
              <Badge badgeContent={pendingPaymentApprovalsCount} color="warning" invisible={pendingPaymentApprovalsCount === 0} max={99}>
                <PaymentIcon />
              </Badge>
            }
            label="Pagamentos"
            iconPosition="start"
            sx={{ fontWeight: 'bold' }}
          />
        )}
        {user?.role === 'system_admin' && <Tab value="invitations" icon={<MailIcon />} label="Convites" iconPosition="start" sx={{ fontWeight: 'bold' }} />}
      </Tabs>

      {/* =========================================
          TAB: MATCHES
         ========================================= */}
      {tabIndex === 'matches' && (
        <Stack spacing={3}>
          <Box sx={{ display: 'flex', justifyContent: 'flex-start', mb: 1 }}>
            <ToggleButtonGroup
              value={matchMode}
              exclusive
              onChange={(e, val) => val && setMatchMode(val)}
              size="small"
              color="primary"
            >
              <ToggleButton value="scores" sx={{ fontWeight: 'bold' }}>
                <Box component="img" src="/icons/icon-48.png" alt="Logo" sx={{ width: 16, height: 16, mr: 1, display: 'inline-block', verticalAlign: 'middle' }} />
                Gerenciar Placares
              </ToggleButton>
              <ToggleButton value="knockout" sx={{ fontWeight: 'bold' }}>
                🏆 Definir Confrontos Eliminatórios
              </ToggleButton>
            </ToggleButtonGroup>
          </Box>

          {matchMode === 'scores' && (
            <>
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

              {matchTimeGroups.length === 0 ? (
                <Alert severity="info" sx={{ borderRadius: 2 }}>
                  Nenhuma partida encontrada para o filtro selecionado.
                </Alert>
              ) : (
                <Stack spacing={3}>
                  {matchTimeGroups.map(group => (
                    <Card key={group.key}>
                      <CardContent sx={{ p: 0 }}>
                        <Box sx={{ px: 3, py: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, flexWrap: 'wrap', borderBottom: '1px solid #1f2937' }}>
                          <Box>
                            <Typography variant="subtitle1" sx={{ fontWeight: 800, fontFamily: 'Outfit' }}>
                              {formatDateTime(group.kickoff_time)}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {group.matches.length} partida(s) neste horário
                            </Typography>
                          </Box>
                          <Button
                            variant="contained"
                            color="primary"
                            startIcon={<SaveIcon />}
                            disabled={savingScoreGroup === group.key}
                            onClick={() => handleSaveScoreGroup(group.key, group.matches)}
                          >
                            {savingScoreGroup === group.key ? 'Salvando...' : 'Salvar este horário'}
                          </Button>
                        </Box>

                        <Stack spacing={1.5} sx={{ p: { xs: 1.5, sm: 2.5 } }}>
                          {group.matches.map(match => {
                            const draft = getScoreDraft(match.id)
                            const isKnockout = match.stage !== 'Group Stage'
                            return (
                              <Box
                                key={match.id}
                                sx={{
                                  p: { xs: 1.5, sm: 2 },
                                  borderRadius: 2,
                                  border: '1px solid',
                                  borderColor: 'divider',
                                  bgcolor: 'background.default'
                                }}
                              >
                                <Stack spacing={1.5}>
                                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} justifyContent="space-between" alignItems={{ xs: 'stretch', sm: 'center' }}>
                                    <Box sx={{ minWidth: 0 }}>
                                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontWeight: 600 }}>
                                        {match.round} · ID #{match.id}
                                      </Typography>
                                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                        {match.ground}
                                      </Typography>
                                    </Box>
                                    <Stack direction="row" spacing={1} alignItems="center" justifyContent={{ xs: 'space-between', sm: 'flex-end' }}>
                                      <Chip label={match.status.replace('_', ' ')} color={match.status === 'score_confirmed' ? 'success' : 'default'} size="small" sx={{ fontWeight: 'bold', textTransform: 'capitalize' }} />
                                      <Select
                                        size="small"
                                        value={match.status}
                                        onChange={(e) => handleStatusChange(match.id, e.target.value)}
                                        sx={{ height: 30, fontSize: '0.75rem', minWidth: 116 }}
                                      >
                                        <MenuItem value="scheduled">Agendado</MenuItem>
                                        <MenuItem value="score_pending_review" disabled>Revisar</MenuItem>
                                        <MenuItem value="score_confirmed" disabled>Confirmado</MenuItem>
                                        <MenuItem value="postponed">Adiado</MenuItem>
                                        <MenuItem value="cancelled">Cancelado</MenuItem>
                                      </Select>
                                    </Stack>
                                  </Stack>

                                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: { xs: 0.75, sm: 1.5 }, width: '100%' }}>
                                    {renderAdminTeamLabel(match, 1)}
                                    {renderScoreInput(match.id, 'score_ft_team1', draft.score_ft_team1)}
                                    <Typography variant="body2" sx={{ fontWeight: 800, color: 'text.secondary' }}>x</Typography>
                                    {renderScoreInput(match.id, 'score_ft_team2', draft.score_ft_team2)}
                                    {renderAdminTeamLabel(match, 2)}
                                  </Box>

                                  {isKnockout && (
                                    <Grid container spacing={1.5}>
                                      <Grid item xs={12} sm={6}>
                                        <Box sx={{ p: 1.25, borderRadius: 2, border: '1px solid #1f2937' }}>
                                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textAlign: 'center', mb: 1 }}>
                                            Prorrogação
                                          </Typography>
                                          <Stack direction="row" spacing={1} justifyContent="center" alignItems="center">
                                            {renderScoreInput(match.id, 'score_et_team1', draft.score_et_team1)}
                                            <Typography variant="body2">x</Typography>
                                            {renderScoreInput(match.id, 'score_et_team2', draft.score_et_team2)}
                                          </Stack>
                                        </Box>
                                      </Grid>
                                      <Grid item xs={12} sm={6}>
                                        <Box sx={{ p: 1.25, borderRadius: 2, border: '1px solid #1f2937' }}>
                                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textAlign: 'center', mb: 1 }}>
                                            Pênaltis
                                          </Typography>
                                          <Stack direction="row" spacing={1} justifyContent="center" alignItems="center">
                                            {renderScoreInput(match.id, 'score_pen_team1', draft.score_pen_team1)}
                                            <Typography variant="body2">x</Typography>
                                            {renderScoreInput(match.id, 'score_pen_team2', draft.score_pen_team2)}
                                          </Stack>
                                        </Box>
                                      </Grid>
                                    </Grid>
                                  )}

                                  <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
                                    {match.status === 'score_pending_review' && (
                                      <Button size="small" variant="contained" color="success" startIcon={<CheckIcon />} onClick={() => handleConfirmScore(match.id)}>
                                        Confirmar
                                      </Button>
                                    )}
                                  </Stack>
                                </Stack>
                              </Box>
                            )
                          })}
                        </Stack>
                      </CardContent>
                    </Card>
                  ))}
                </Stack>
              )}
            </>
          )}

          {matchMode === 'knockout' && (
            <Box>
              {knockoutLoading && !knockoutSetup ? (
                <Alert severity="info">Carregando confrontos...</Alert>
              ) : !knockoutSetup ? (
                <Alert severity="warning">
                  {error || 'Não foi possível carregar a configuração do mata-mata. Certifique-se de que o seed de dados inicial (times/estádios/jogos) foi realizado.'}
                </Alert>
              ) : (
                <Grid container spacing={3}>
                  <Grid item xs={12} md={8}>
                    <Stack spacing={3}>
                      {/* Top actions card */}
                      <Card>
                        <CardContent sx={{ p: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
                          <Box sx={{ maxWidth: '60%' }}>
                            <Typography variant="subtitle1" sx={{ fontWeight: 'bold', fontFamily: 'Outfit' }}>
                              Definição Automática de Confrontos
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              Sincronize com a API do football-data.org ou aplique as sugestões baseadas na classificação da Fase de Grupos.
                            </Typography>
                          </Box>
                          <Stack direction="row" spacing={2}>
                            <Button
                              variant="outlined"
                              color="secondary"
                              onClick={handleApplyAllSuggestions}
                              disabled={!knockoutSetup || knockoutSetup.matches.length === 0}
                            >
                              Usar Todas as Sugestões
                            </Button>
                            <Button
                              variant="contained"
                              color="primary"
                              startIcon={<SyncIcon />}
                              onClick={handleTriggerFootballDataFixturesSync}
                              disabled={syncFixturesLoading}
                            >
                              {syncFixturesLoading ? 'Sincronizando...' : 'Sincronizar via API'}
                            </Button>
                          </Stack>
                        </CardContent>
                      </Card>

                      {/* Matches list */}
                      {!knockoutSetup || knockoutSetup.matches.length === 0 ? (
                        <Alert severity="info">Nenhum jogo eliminatório encontrado.</Alert>
                      ) : (
                        knockoutSetup.matches.map(m => {
                          const sug1 = m.suggested_team1
                          const sug2 = m.suggested_team2
                          const formVal = knockoutForm[m.id] || { team1_name: '', team2_name: '' }
                          const isModified = formVal.team1_name !== m.team1_name || formVal.team2_name !== m.team2_name
                          
                          return (
                            <Card key={m.id} sx={{ borderLeft: '4px solid', borderColor: m.team1_is_placeholder || m.team2_is_placeholder ? 'warning.main' : 'success.main' }}>
                              <CardContent sx={{ p: 3 }}>
                                <Stack spacing={2}>
                                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <Box>
                                      <Typography variant="subtitle2" color="primary" sx={{ fontWeight: 'bold' }}>
                                        {m.stage} · {m.round}
                                      </Typography>
                                      <Typography variant="caption" color="text.secondary">
                                        ID #{m.id} · {m.date} {m.time_str}
                                      </Typography>
                                    </Box>
                                    <Chip
                                      label={m.team1_is_placeholder || m.team2_is_placeholder ? 'Aguardando Times' : 'Confronto Definido'}
                                      color={m.team1_is_placeholder || m.team2_is_placeholder ? 'warning' : 'success'}
                                      size="small"
                                      sx={{ fontWeight: 'bold' }}
                                    />
                                  </Box>
                                  
                                  {/* Current Teams Display */}
                                  <Box sx={{ bgcolor: 'action.hover', p: 1.5, borderRadius: 1, display: 'flex', justifyContent: 'space-around', alignItems: 'center' }}>
                                    <Typography variant="body2" sx={{ fontWeight: m.team1_is_placeholder ? 'normal' : 'bold', color: m.team1_is_placeholder ? 'text.secondary' : 'text.primary' }}>
                                      {m.team1_name}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">VS</Typography>
                                    <Typography variant="body2" sx={{ fontWeight: m.team2_is_placeholder ? 'normal' : 'bold', color: m.team2_is_placeholder ? 'text.secondary' : 'text.primary' }}>
                                      {m.team2_name}
                                    </Typography>
                                  </Box>

                                  {/* Selectors and Action */}
                                  <Grid container spacing={2} alignItems="center">
                                    <Grid item xs={12} sm={4.5}>
                                      <Autocomplete
                                        size="small"
                                        options={m.possible_teams1 || []}
                                        getOptionLabel={(option) => option.name}
                                        value={(m.possible_teams1 || []).find(t => t.name === formVal.team1_name) || null}
                                        onChange={(event, newValue) => {
                                          setKnockoutForm(prev => ({
                                            ...prev,
                                            [m.id]: {
                                              ...prev[m.id],
                                              team1_name: newValue ? newValue.name : ''
                                            }
                                          }))
                                        }}
                                        renderInput={(params) => <TextField {...params} label="Time 1" />}
                                      />
                                      {sug1 && formVal.team1_name !== sug1 && (
                                        <Button
                                          size="small"
                                          color="secondary"
                                          onClick={() => handleApplySuggestions(m.id, sug1, formVal.team2_name || sug2)}
                                          sx={{ mt: 0.5, fontSize: '0.75rem', p: 0, minWidth: 0, textTransform: 'none' }}
                                        >
                                          Sugerido: {sug1}
                                        </Button>
                                      )}
                                    </Grid>
                                    <Grid item xs={12} sm={1} align="center">
                                      <Typography variant="body2" color="text.secondary">x</Typography>
                                    </Grid>
                                    <Grid item xs={12} sm={4.5}>
                                      <Autocomplete
                                        size="small"
                                        options={m.possible_teams2 || []}
                                        getOptionLabel={(option) => option.name}
                                        value={(m.possible_teams2 || []).find(t => t.name === formVal.team2_name) || null}
                                        onChange={(event, newValue) => {
                                          setKnockoutForm(prev => ({
                                            ...prev,
                                            [m.id]: {
                                              ...prev[m.id],
                                              team2_name: newValue ? newValue.name : ''
                                            }
                                          }))
                                        }}
                                        renderInput={(params) => <TextField {...params} label="Time 2" />}
                                      />
                                      {sug2 && formVal.team2_name !== sug2 && (
                                        <Button
                                          size="small"
                                          color="secondary"
                                          onClick={() => handleApplySuggestions(m.id, formVal.team1_name || sug1, sug2)}
                                          sx={{ mt: 0.5, fontSize: '0.75rem', p: 0, minWidth: 0, textTransform: 'none' }}
                                        >
                                          Sugerido: {sug2}
                                        </Button>
                                      )}
                                    </Grid>
                                    <Grid item xs={12} sm={2}>
                                      <Button
                                        variant="contained"
                                        color="primary"
                                        fullWidth
                                        disabled={!isModified || definingTeamsMatchId === m.id}
                                        onClick={() => handleSaveKnockoutMatch(m.id)}
                                      >
                                        {definingTeamsMatchId === m.id ? 'Salvar...' : 'Salvar'}
                                      </Button>
                                    </Grid>
                                  </Grid>
                                </Stack>
                              </CardContent>
                            </Card>
                          )
                        })
                      )}
                    </Stack>
                  </Grid>

                  {/* Reference standings column */}
                  <Grid item xs={12} md={4}>
                    <Card sx={{ position: 'sticky', top: 20 }}>
                      <CardContent sx={{ p: 2 }}>
                        <Typography variant="h6" sx={{ mb: 2, fontWeight: 700, fontFamily: 'Outfit' }}>
                          Classificação de Referência
                        </Typography>
                        
                        <FormControl size="small" fullWidth sx={{ mb: 2 }}>
                          <InputLabel>Grupo / Classificação</InputLabel>
                          <Select
                            value={selectedRefGroup}
                            label="Grupo / Classificação"
                            onChange={(e) => setSelectedRefGroup(e.target.value)}
                          >
                            {Object.keys(knockoutSetup.groups || {}).sort().map(g => (
                              <MenuItem key={g} value={g}>{g}</MenuItem>
                            ))}
                            <MenuItem value="third_placed">Melhores 3º Colocados</MenuItem>
                          </Select>
                        </FormControl>

                        {selectedRefGroup === 'third_placed' ? (
                          <TableContainer component={Paper} variant="outlined">
                            <Table size="small">
                              <TableHead>
                                <TableRow>
                                  <TableCell sx={{ fontWeight: 'bold', px: 1 }}>Pos</TableCell>
                                  <TableCell sx={{ fontWeight: 'bold', px: 1 }}>Time</TableCell>
                                  <TableCell sx={{ fontWeight: 'bold', px: 1 }} align="right">Pts</TableCell>
                                  <TableCell sx={{ fontWeight: 'bold', px: 1 }} align="right">SG</TableCell>
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                {(knockoutSetup.third_placed || []).map((t, idx) => (
                                  <TableRow key={t.team_name} sx={{ bgcolor: idx < 8 ? 'action.selected' : 'transparent' }}>
                                    <TableCell sx={{ px: 1 }}>{idx + 1}</TableCell>
                                    <TableCell sx={{ px: 1, fontWeight: idx < 8 ? 'bold' : 'normal' }}>
                                      {t.team_name} ({t.group_name.replace('Grupo ', '')})
                                    </TableCell>
                                    <TableCell sx={{ px: 1 }} align="right">{t.points}</TableCell>
                                    <TableCell sx={{ px: 1 }} align="right">{t.goal_difference}</TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </TableContainer>
                        ) : (
                          <TableContainer component={Paper} variant="outlined">
                            <Table size="small">
                              <TableHead>
                                <TableRow>
                                  <TableCell sx={{ fontWeight: 'bold', px: 1 }}>Pos</TableCell>
                                  <TableCell sx={{ fontWeight: 'bold', px: 1 }}>Time</TableCell>
                                  <TableCell sx={{ fontWeight: 'bold', px: 1 }} align="right">Pts</TableCell>
                                  <TableCell sx={{ fontWeight: 'bold', px: 1 }} align="right">SG</TableCell>
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                {(knockoutSetup.groups?.[selectedRefGroup] || []).map((t, idx) => (
                                  <TableRow key={t.team_name} sx={{ bgcolor: idx < 2 ? 'action.selected' : 'transparent' }}>
                                    <TableCell sx={{ px: 1 }}>{idx + 1}</TableCell>
                                    <TableCell sx={{ px: 1, fontWeight: idx < 2 ? 'bold' : 'normal' }}>{t.team_name}</TableCell>
                                    <TableCell sx={{ px: 1 }} align="right">{t.points}</TableCell>
                                    <TableCell sx={{ px: 1 }} align="right">{t.goal_difference}</TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </TableContainer>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              )}
            </Box>
          )}
        </Stack>
      )}

      {/* ==========================================
          TAB 1: INTEGRATION / SYNC
         ========================================== */}
      {tabIndex === 'sync' && (
        <Stack spacing={4}>
          <Card>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2 }}>
                🔄 Resultados Oficiais via API
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                A API oficial consulta partidas já encerradas, preenche placares disponíveis, recalcula pontuação e registra auditoria automaticamente. Use esta ação para forçar uma consulta manual fora da rotina agendada.
              </Typography>
              <Grid container spacing={2} sx={{ mb: 3 }}>
                <Grid item xs={12} sm={4}>
                  <Box sx={{ p: 2, borderRadius: 2, border: '1px solid #1f2937', bgcolor: 'background.default' }}>
	                    <Typography variant="caption" color="text.secondary">Revisão manual exibida</Typography>
                    <Typography variant="h5" sx={{ fontWeight: 800 }}>{matches.filter(m => m.status === 'score_pending_review').length}</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Box sx={{ p: 2, borderRadius: 2, border: '1px solid #1f2937', bgcolor: 'background.default' }}>
	                    <Typography variant="caption" color="text.secondary">Horários pendentes exibidos</Typography>
                    <Typography variant="h5" sx={{ fontWeight: 800 }}>{matchTimeGroups.length}</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Box sx={{ p: 2, borderRadius: 2, border: '1px solid #1f2937', bgcolor: 'background.default' }}>
                    <Typography variant="caption" color="text.secondary">Diffs legados pendentes</Typography>
                    <Typography variant="h5" sx={{ fontWeight: 800 }}>{syncDiffs.length}</Typography>
                  </Box>
                </Grid>
              </Grid>
              <Button variant="contained" color="primary" startIcon={<SyncIcon />} onClick={handleTriggerSyncJob} disabled={syncLoading}>
                Buscar resultados oficiais agora
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardContent sx={{ p: 4 }}>
              <Stack spacing={3}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: { xs: 'stretch', sm: 'center' }, gap: 2, flexDirection: { xs: 'column', sm: 'row' } }}>
                  <Box>
                    <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit' }}>
                      Status da sincronização football-data
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Atualiza automaticamente a cada 5 segundos enquanto esta aba está aberta.
                    </Typography>
                  </Box>
                  <Button
                    variant="outlined"
                    startIcon={<RefreshIcon />}
                    onClick={() => loadFootballDataLogs()}
                    disabled={footballDataLogsLoading}
                  >
                    Atualizar logs
                  </Button>
                </Box>

                {footballDataLogs.length === 0 ? (
                  <Alert severity="info">
                    Nenhuma consulta ao football-data registrada ainda.
                  </Alert>
                ) : (
                  <>
                    <Grid container spacing={2}>
                      <Grid item xs={12} sm={3}>
                        <Box sx={{ p: 2, borderRadius: 2, border: '1px solid #1f2937', bgcolor: 'background.default' }}>
                          <Typography variant="caption" color="text.secondary">Último status</Typography>
                          <Box sx={{ mt: 1 }}>
                            <Chip
                              label={getFootballDataStatusLabel(footballDataLogs[0].status)}
                              color={getFootballDataStatusColor(footballDataLogs[0].status)}
                              size="small"
                            />
                          </Box>
                        </Box>
                      </Grid>
                      <Grid item xs={12} sm={3}>
                        <Box sx={{ p: 2, borderRadius: 2, border: '1px solid #1f2937', bgcolor: 'background.default' }}>
                          <Typography variant="caption" color="text.secondary">Última consulta</Typography>
                          <Typography variant="body2" sx={{ fontWeight: 700, mt: 1 }}>
                            {formatDateTime(footballDataLogs[0].started_at)}
                          </Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={6} sm={3}>
                        <Box sx={{ p: 2, borderRadius: 2, border: '1px solid #1f2937', bgcolor: 'background.default' }}>
                          <Typography variant="caption" color="text.secondary">Horários checados</Typography>
                          <Typography variant="h5" sx={{ fontWeight: 800 }}>{footballDataLogs[0].checked_groups}</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={6} sm={3}>
                        <Box sx={{ p: 2, borderRadius: 2, border: '1px solid #1f2937', bgcolor: 'background.default' }}>
                          <Typography variant="caption" color="text.secondary">Placares aplicados</Typography>
                          <Typography variant="h5" sx={{ fontWeight: 800 }}>{footballDataLogs[0].updated_matches}</Typography>
                        </Box>
                      </Grid>
                    </Grid>

                    <Stack spacing={1.5}>
                      {footballDataLogs.map(log => {
                        const events = log.details?.events || []
                        return (
                          <Accordion key={log.id} disableGutters sx={{ bgcolor: 'background.default', border: '1px solid #1f2937' }}>
                            <AccordionSummary expandIcon={<ExpandIcon />}>
                              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25} alignItems={{ xs: 'flex-start', sm: 'center' }} sx={{ width: '100%' }}>
                                <Chip
                                  label={getFootballDataStatusLabel(log.status)}
                                  color={getFootballDataStatusColor(log.status)}
                                  size="small"
                                />
                                <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                  #{log.id} - {log.trigger === 'scheduled' ? 'Agendada' : 'Manual'} - {formatDateTime(log.started_at)}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  {log.checked_groups} horário(s), {log.updated_matches} placar(es), {log.errors?.length || 0} erro(s)
                                </Typography>
                              </Stack>
                            </AccordionSummary>
                            <AccordionDetails>
                              <Stack spacing={1.5}>
                                {log.errors?.length > 0 && (
                                  <Alert severity="error">
                                    {log.errors.join(' | ')}
                                  </Alert>
                                )}
                                {events.length === 0 ? (
                                  <Typography variant="body2" color="text.secondary">
                                    Nenhum evento detalhado gravado para esta execução.
                                  </Typography>
                                ) : (
                                  events.map((event, index) => (
                                    <Box key={`${log.id}-${index}`} sx={{ p: 1.5, borderRadius: 1.5, border: '1px solid #1f2937' }}>
                                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ xs: 'flex-start', sm: 'center' }}>
                                        <Chip
                                          size="small"
                                          label={event.level || 'info'}
                                          color={getFootballDataStatusColor(event.level === 'info' ? 'running' : event.level)}
                                          variant="outlined"
                                        />
                                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                          {event.message}
                                        </Typography>
                                        <Typography variant="caption" color="text.secondary">
                                          {event.timestamp ? formatDateTime(event.timestamp) : ''}
                                        </Typography>
                                      </Stack>
                                      {renderFootballDataEventExtra(event)}
                                    </Box>
                                  ))
                                )}
                              </Stack>
                            </AccordionDetails>
                          </Accordion>
                        )
                      })}
                    </Stack>
                  </>
                )}
              </Stack>
            </CardContent>
          </Card>

          <Card>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                Openfootball legado e carga inicial
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                O openfootball permanece útil para seed de times, estádios e tabela original. A varredura legada de resultados fica disponível apenas para auditoria/compatibilidade e não deve ser o fluxo principal de placares.
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <Button variant="outlined" color="secondary" startIcon={<SyncIcon />} onClick={handleTriggerInitialSeed} disabled={syncLoading}>
                  Seed inicial de tabela
                </Button>
                <Button variant="outlined" color="primary" startIcon={<SyncIcon />} onClick={handleTriggerLegacyOpenfootballSync} disabled={syncLoading}>
                  Rodar sync legado openfootball
                </Button>
              </Stack>
            </CardContent>
          </Card>

          <Card>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
                ⌛ Diffs legados pendentes de revisão ({syncDiffs.length})
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Se uma sincronização legada encontrar diferença em placar já confirmado por administrador, ela fica listada aqui para aprovação manual. O fluxo principal pela API oficial atualiza apenas partidas ainda sem placar confirmado.
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
      {tabIndex === 'scoring' && user?.role === 'system_admin' && (
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

	          <Card>
	            <CardContent sx={{ p: 4 }}>
	              <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 3 }}>
	                ⏱️ Bloqueio de Palpites
	              </Typography>
	              <Box component="form" onSubmit={handleUpdatePredictionLockHours}>
	                <Grid container spacing={2} alignItems="center">
	                  <Grid item xs={12} sm={6} md={4}>
	                    <TextField
	                      label="Horas antes do jogo"
	                      type="number"
	                      size="small"
	                      fullWidth
	                      required
	                      value={predictionLockHours}
	                      onChange={(e) => setPredictionLockHours(e.target.value)}
	                      inputProps={{ min: 0, max: predictionLockMaxHours, step: 1 }}
	                    />
	                  </Grid>
	                  <Grid item xs={12} sm={6} md={3}>
	                    <Button type="submit" variant="contained" color="primary" startIcon={<SaveIcon />} fullWidth>
	                      Salvar
	                    </Button>
	                  </Grid>
	                </Grid>
	              </Box>
	            </CardContent>
	          </Card>

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
      {tabIndex === 'announcements' && user?.role === 'system_admin' && (
        <Stack spacing={4} sx={{ maxWidth: 650, mx: 'auto' }}>
          <Card>
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

          <Card>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2 }}>
                💬 Configurar Mensagem de Cobrança
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Configure o texto que será enviado no grupo do WhatsApp ao cobrar devedores. Use os placeholders disponíveis abaixo para enriquecer a mensagem.
              </Typography>
              <Box component="form" onSubmit={handleSaveChargeTemplate}>
                <Grid container spacing={4}>
                  <Grid item xs={12} md={7}>
                    <Stack spacing={3}>
                      <TextField
                        label="Modelo de Mensagem de Cobrança"
                        variant="outlined"
                        required
                        fullWidth
                        multiline
                        rows={10}
                        value={chargeTemplate}
                        onChange={(e) => setChargeTemplate(e.target.value)}
                        placeholder="Escreva a mensagem de cobrança..."
                      />

                      <Box>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, fontFamily: 'Outfit' }}>
                          Placeholders Disponíveis
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                          Dica: Clique em qualquer um dos placeholders abaixo para adicioná-lo ao final da sua mensagem:
                        </Typography>
                        <Grid container spacing={1.5}>
                          {[
                            { tag: '{{devedores}}', label: 'Lista de Devedores', desc: 'Nomes dos devedores separados por linha.' },
                            { tag: '{{aprovados}}', label: 'Cadastros Aprovados', desc: 'Número total de participantes com cadastro ativo (excluindo admins).' },
                            { tag: '{{aprovados_pagos}}', label: 'Inscrições Pagas', desc: 'Participantes ativos com pagamento aprovado (excluindo admins).' },
                            { tag: '{{valor}}', label: 'Valor Total Aprovado', desc: 'Valor arrecadado dos participantes aprovados (ex: R$ 500,00).' },
                            { tag: '{{total_cadastrados}}', label: 'Total Cadastrados', desc: 'Número total de participantes ativos (excluindo admins).' },
                            { tag: '{{devedores_qtd}}', label: 'Qtd. de Devedores', desc: 'Número de devedores pendentes (excluindo admins).' },
                            { tag: '{{taxa_inscricao}}', label: 'Taxa de Inscrição', desc: 'Valor individual da taxa de inscrição (ex: R$ 50,00).' }
                          ].map((ph) => (
                            <Grid item xs={12} sm={6} key={ph.tag}>
                              <Paper
                                variant="outlined"
                                sx={{
                                  p: 1.5,
                                  cursor: 'pointer',
                                  '&:hover': { bgcolor: 'action.hover', borderColor: 'primary.main' },
                                  transition: 'all 0.2s',
                                  height: '100%',
                                  display: 'flex',
                                  flexDirection: 'column',
                                  justifyContent: 'center'
                                }}
                                onClick={() => {
                                  setChargeTemplate(prev => prev + ph.tag)
                                }}
                              >
                                <Typography sx={{ fontFamily: 'monospace', fontWeight: 'bold', color: 'primary.main', fontSize: '0.85rem' }}>
                                  {ph.tag}
                                </Typography>
                                <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', mt: 0.5 }}>
                                  {ph.label}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: 'block', lineHeight: 1.2, mb: 1.5 }}>
                                  {ph.desc}
                                </Typography>
                                <Box sx={{ mt: 'auto', pt: 1, borderTop: '1px dashed', borderColor: 'divider', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                  <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.secondary', fontSize: '0.75rem' }}>
                                    Valor atual:
                                  </Typography>
                                  <Typography variant="caption" sx={{ fontFamily: 'monospace', fontWeight: 'bold', color: 'text.primary', fontSize: '0.75rem' }}>
                                    {ph.tag === '{{devedores}}' ? (placeholderValues.devedores_qtd ? `${placeholderValues.devedores_qtd} devedores` : 'Nenhum') :
                                     ph.tag === '{{aprovados}}' ? (placeholderValues.aprovados ?? 0) :
                                     ph.tag === '{{aprovados_pagos}}' ? (placeholderValues.aprovados_pagos ?? 0) :
                                     ph.tag === '{{valor}}' ? (placeholderValues.valor || 'R$ 0,00') :
                                     ph.tag === '{{total_cadastrados}}' ? (placeholderValues.total_cadastrados ?? 0) :
                                     ph.tag === '{{devedores_qtd}}' ? (placeholderValues.devedores_qtd ?? 0) :
                                     ph.tag === '{{taxa_inscricao}}' ? (placeholderValues.taxa_inscricao || 'R$ 0,00') : '-'}
                                  </Typography>
                                </Box>
                              </Paper>
                            </Grid>
                          ))}
                        </Grid>
                      </Box>

                      <Button type="submit" variant="contained" color="secondary" size="large" disabled={savingTemplate} sx={{ alignSelf: 'flex-start' }}>
                        {savingTemplate ? 'Salvando...' : 'Salvar Modelo de Cobrança'}
                      </Button>
                    </Stack>
                  </Grid>

                  <Grid item xs={12} md={5}>
                    <Box
                      sx={{
                        border: '1px solid',
                        borderColor: 'divider',
                        borderRadius: 3,
                        overflow: 'hidden',
                        height: '100%',
                        minHeight: 450,
                        display: 'flex',
                        flexDirection: 'column',
                        bgcolor: 'background.default'
                      }}
                    >
                      <Box
                        sx={{
                          bgcolor: '#075E54',
                          color: '#fff',
                          px: 2.5,
                          py: 2,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 1.5
                        }}
                      >
                        <Box
                          sx={{
                            width: 36,
                            height: 36,
                            borderRadius: '50%',
                            bgcolor: '#128C7E',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontWeight: 'bold',
                            fontSize: '1.1rem'
                          }}
                        >
                          🏆
                        </Box>
                        <Box sx={{ minWidth: 0 }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 'bold', display: 'block', lineHeight: 1.2 }}>
                            Grupo Oficial - Bolão Copa 2026
                          </Typography>
                          <Typography variant="caption" sx={{ opacity: 0.8, display: 'block', lineHeight: 1.2 }}>
                            Mensagem Automática (WhatsApp)
                          </Typography>
                        </Box>
                      </Box>

                      <Box
                        sx={{
                          flexGrow: 1,
                          p: 2.5,
                          backgroundImage: 'radial-gradient(circle, #efeae2 20%, transparent 20%), radial-gradient(circle, #efeae2 20%, transparent 20%)',
                          backgroundSize: '16px 16px',
                          backgroundPosition: '0 0, 8px 8px',
                          bgcolor: '#f4f1eb',
                          overflowY: 'auto',
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'flex-start'
                        }}
                      >
                        <Box
                          sx={{
                            bgcolor: '#d9fdd3',
                            color: '#303030',
                            borderRadius: '8px 8px 0px 8px',
                            boxShadow: '0 1px 0.5px rgba(0,0,0,0.13)',
                            p: 2,
                            maxWidth: '90%',
                            alignSelf: 'flex-end',
                            position: 'relative',
                            mb: 1,
                            minWidth: 180
                          }}
                        >
                          <Typography
                            variant="body2"
                            sx={{
                              whiteSpace: 'pre-wrap',
                              fontFamily: 'Segoe UI, Helvetica, Arial, sans-serif',
                              fontSize: '0.9rem',
                              lineHeight: 1.4,
                              wordBreak: 'break-word',
                              pb: 1.5
                            }}
                          >
                            {compilePreview(chargeTemplate) || 'Escreva o modelo de mensagem de cobrança no editor...'}
                          </Typography>
                          <Box
                            sx={{
                              position: 'absolute',
                              bottom: 4,
                              right: 8,
                              display: 'flex',
                              alignItems: 'center',
                              gap: 0.5
                            }}
                          >
                            <Typography variant="caption" sx={{ fontSize: '0.65rem', color: '#667781' }}>
                              {new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                            </Typography>
                            <Box sx={{ color: '#53bdeb', display: 'flex', fontSize: 12, fontWeight: 'bold' }}>
                              ✔✔
                            </Box>
                          </Box>
                        </Box>
                      </Box>
                    </Box>
                  </Grid>
                </Grid>
              </Box>
            </CardContent>
          </Card>

          <Card>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2 }}>
                💰 Configurar Confirmação de Pagamento
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                Configure o texto que será enviado no grupo do WhatsApp ao aprovar o pagamento de um participante. Use os placeholders disponíveis abaixo para enriquecer a mensagem.
              </Typography>
              <Box component="form" onSubmit={handleSaveApprovalTemplate}>
                <Grid container spacing={4}>
                  <Grid item xs={12} md={7}>
                    <Stack spacing={3}>
                      <TextField
                        label="Modelo de Confirmação de Pagamento"
                        variant="outlined"
                        required
                        fullWidth
                        multiline
                        rows={10}
                        value={approvalTemplate}
                        onChange={(e) => setApprovalTemplate(e.target.value)}
                        placeholder="Escreva a mensagem de aprovação de pagamento..."
                      />

                      <Box>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, fontFamily: 'Outfit' }}>
                          Placeholders Disponíveis
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                          Dica: Clique em qualquer um dos placeholders abaixo para adicioná-lo ao final da sua mensagem:
                        </Typography>
                        <Grid container spacing={1.5}>
                          {[
                            { tag: '{{usuario}}', label: 'Nome do Participante', desc: 'Nome do participante que teve o pagamento aprovado.' },
                            { tag: '{{prizepool}}', label: 'Tabela de Premiação', desc: 'Prêmios estimados para 1º, 2º e 3º lugares (calculados automaticamente).' },
                            { tag: '{{valor}}', label: 'Valor Total Aprovado', desc: 'Valor arrecadado dos participantes aprovados (ex: R$ 8.250,00).' },
                            { tag: '{{aprovados_pagos}}', label: 'Inscrições Pagas', desc: 'Participantes ativos com pagamento aprovado (excluindo admins).' },
                            { tag: '{{taxa_inscricao}}', label: 'Taxa de Inscrição', desc: 'Valor individual da taxa de inscrição (ex: R$ 150,00).' }
                          ].map((ph) => (
                            <Grid item xs={12} sm={6} key={ph.tag}>
                              <Paper
                                variant="outlined"
                                sx={{
                                  p: 1.5,
                                  cursor: 'pointer',
                                  '&:hover': { bgcolor: 'action.hover', borderColor: 'primary.main' },
                                  transition: 'all 0.2s',
                                  height: '100%',
                                  display: 'flex',
                                  flexDirection: 'column',
                                  justifyContent: 'center'
                                }}
                                onClick={() => {
                                  setApprovalTemplate(prev => prev + ph.tag)
                                }}
                              >
                                <Typography sx={{ fontFamily: 'monospace', fontWeight: 'bold', color: 'primary.main', fontSize: '0.85rem' }}>
                                  {ph.tag}
                                </Typography>
                                <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', mt: 0.5 }}>
                                  {ph.label}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: 'block', lineHeight: 1.2, mb: 1.5 }}>
                                  {ph.desc}
                                </Typography>
                                <Box sx={{ mt: 'auto', pt: 1, borderTop: '1px dashed', borderColor: 'divider', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                  <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.secondary', fontSize: '0.75rem' }}>
                                    Valor atual:
                                  </Typography>
                                  <Typography variant="caption" sx={{ fontFamily: 'monospace', fontWeight: 'bold', color: 'text.primary', fontSize: '0.75rem', whiteSpace: 'pre-wrap', textAlign: 'right' }}>
                                    {ph.tag === '{{usuario}}' ? (approvalValues.usuario || 'Fulano de Tal') :
                                     ph.tag === '{{prizepool}}' ? (approvalValues.prizepool || '-') :
                                     ph.tag === '{{valor}}' ? (approvalValues.valor || 'R$ 0,00') :
                                     ph.tag === '{{aprovados_pagos}}' ? (approvalValues.aprovados_pagos ?? 0) :
                                     ph.tag === '{{taxa_inscricao}}' ? (approvalValues.taxa_inscricao || 'R$ 0,00') : '-'}
                                  </Typography>
                                </Box>
                              </Paper>
                            </Grid>
                          ))}
                        </Grid>
                      </Box>

                      <Button type="submit" variant="contained" color="secondary" size="large" disabled={savingApprovalTemplate} sx={{ alignSelf: 'flex-start' }}>
                        {savingApprovalTemplate ? 'Salvando...' : 'Salvar Modelo de Confirmação'}
                      </Button>
                    </Stack>
                  </Grid>

                  <Grid item xs={12} md={5}>
                    <Box
                      sx={{
                        border: '1px solid',
                        borderColor: 'divider',
                        borderRadius: 3,
                        overflow: 'hidden',
                        height: '100%',
                        minHeight: 450,
                        display: 'flex',
                        flexDirection: 'column',
                        bgcolor: 'background.default'
                      }}
                    >
                      <Box
                        sx={{
                          bgcolor: '#075E54',
                          color: '#fff',
                          px: 2.5,
                          py: 2,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 1.5
                        }}
                      >
                        <Box
                          sx={{
                            width: 36,
                            height: 36,
                            borderRadius: '50%',
                            bgcolor: '#128C7E',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontWeight: 'bold',
                            fontSize: '1.1rem'
                          }}
                        >
                          🏆
                        </Box>
                        <Box sx={{ minWidth: 0 }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 'bold', display: 'block', lineHeight: 1.2 }}>
                            Grupo Oficial - Bolão Copa 2026
                          </Typography>
                          <Typography variant="caption" sx={{ opacity: 0.8, display: 'block', lineHeight: 1.2 }}>
                            Mensagem Automática (WhatsApp)
                          </Typography>
                        </Box>
                      </Box>

                      <Box
                        sx={{
                          flexGrow: 1,
                          p: 2.5,
                          backgroundImage: 'radial-gradient(circle, #efeae2 20%, transparent 20%), radial-gradient(circle, #efeae2 20%, transparent 20%)',
                          backgroundSize: '16px 16px',
                          backgroundPosition: '0 0, 8px 8px',
                          bgcolor: '#f4f1eb',
                          overflowY: 'auto',
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'flex-start'
                        }}
                      >
                        <Box
                          sx={{
                            bgcolor: '#d9fdd3',
                            color: '#303030',
                            borderRadius: '8px 8px 0px 8px',
                            boxShadow: '0 1px 0.5px rgba(0,0,0,0.13)',
                            p: 2,
                            maxWidth: '90%',
                            alignSelf: 'flex-end',
                            position: 'relative',
                            mb: 1,
                            minWidth: 180
                          }}
                        >
                          <Typography
                            variant="body2"
                            sx={{
                              whiteSpace: 'pre-wrap',
                              fontFamily: 'Segoe UI, Helvetica, Arial, sans-serif',
                              fontSize: '0.9rem',
                              lineHeight: 1.4,
                              wordBreak: 'break-word',
                              pb: 1.5
                            }}
                          >
                            {compileApprovalPreview(approvalTemplate) || 'Escreva o modelo de mensagem de aprovação de pagamento...'}
                          </Typography>
                          <Box
                            sx={{
                              position: 'absolute',
                              bottom: 4,
                              right: 8,
                              display: 'flex',
                              alignItems: 'center',
                              gap: 0.5
                            }}
                          >
                            <Typography variant="caption" sx={{ fontSize: '0.65rem', color: '#667781' }}>
                              {new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                            </Typography>
                            <Box sx={{ color: '#53bdeb', display: 'flex', fontSize: 12, fontWeight: 'bold' }}>
                              ✔✔
                            </Box>
                          </Box>
                        </Box>
                      </Box>
                    </Box>
                  </Grid>
                </Grid>
              </Box>
            </CardContent>
          </Card>
        </Stack>
      )}

      {/* ==========================================
          TAB 4: USERS / RBAC OVERRIDES (System Admin Only)
         ========================================== */}
      {tabIndex === 'users' && user?.role === 'system_admin' && (
        <Stack spacing={3}>
          <Card>
            <CardContent sx={{ p: 2 }}>
              <Stack spacing={2}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: { xs: 'stretch', sm: 'center' }, gap: 2, flexDirection: { xs: 'column', sm: 'row' } }}>
                  <Box>
                    <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit' }}>
                      👥 Usuários & Acessos
                    </Typography>
                    <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap', rowGap: 1 }}>
                      <Chip label={`${totalUsersCount} usuário(s)`} size="small" />
                      <Chip label={`${activeUsersCount} ativo(s)`} color="success" size="small" />
                      <Chip label={`${inactiveUsersCount} inativo(s)`} color="warning" variant="outlined" size="small" />
                    </Stack>
                  </Box>
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={hideActiveUsers}
                        onChange={(e) => setHideActiveUsers(e.target.checked)}
                        size="small"
                      />
                    }
                    label="Ocultar ativos"
                    sx={{ m: 0 }}
                  />
                </Box>
                <TextField
                  label="Buscar usuários por username, nome ou e-mail..."
                  variant="outlined"
                  size="small"
                  fullWidth
                  value={userSearch}
                  onChange={(e) => setUserSearch(e.target.value)}
                />
              </Stack>
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
	                  <TableCell align="center">Ações</TableCell>
	                </TableRow>
              </TableHead>
              <TableBody>
                {filteredUsers.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                      {hideActiveUsers ? 'Nenhum usuário inativo para exibir.' : 'Nenhum usuário encontrado.'}
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredUsers.map(u => (
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
                        <Stack spacing={0.5} alignItems="center">
                          <Switch
                            checked={u.is_active}
                            disabled={u.id === user.id}
                            color="success"
                            onChange={() => handleToggleUserActive(u.id, u.is_active)}
                          />
                          <Chip
                            label={u.is_active ? 'Ativo' : 'Inativo'}
                            color={u.is_active ? 'success' : 'warning'}
                            size="small"
                            variant={u.is_active ? 'filled' : 'outlined'}
                          />
                        </Stack>
                      </TableCell>
                      <TableCell align="center">
                        {new Date(u.created_at).toLocaleDateString('pt-BR')}
                      </TableCell>
                      <TableCell align="center">
                        <Button
                          size="small"
                          variant="outlined"
                          color="error"
                          disabled={u.id === user.id}
                          onClick={() => handleOpenDeleteUserDialog(u)}
                        >
                          Remover
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      )}

      {/* ==========================================
          TAB 5: AUDIT LOGS & CSV EXPORTS (System Admin Only)
         ========================================== */}
      {tabIndex === 'audit' && user?.role === 'system_admin' && (
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
      {tabIndex === 'payments' && (user?.role === 'system_admin' || user?.role === 'score_admin') && (
        <Grid container spacing={3}>
          {/* Pix Config Form */}
          {user?.role === 'system_admin' && (
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
          )}

          {/* User Payments Submissions Table */}
          <Grid item xs={12} md={user?.role === 'system_admin' ? 8 : 12}>
            <TableContainer
              component={Paper}
              sx={{
                borderRadius: 3,
                overflowX: 'hidden',
                '& .MuiTableCell-root': {
                  px: { xs: 0.5, sm: 1.5 },
                  py: { xs: 1, sm: 1.5 }
                }
              }}
            >
              <Box sx={{ p: 3, display: 'flex', justifyContent: 'space-between', alignItems: { xs: 'stretch', sm: 'center' }, gap: 2, flexDirection: { xs: 'column', sm: 'row' } }}>
                <Box>
                  <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit' }}>
                    👥 Comprovantes de Inscrição
                  </Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap', rowGap: 1 }}>
                    <Chip
                      label={`${pendingPaymentApprovalsCount} pendente(s) de aprovação`}
                      color="warning"
                      size="small"
                      sx={{ fontWeight: 'bold' }}
                    />
                    <Chip
                      label={`${paymentDebtors.length} sem pagamento aprovado`}
                      variant="outlined"
                      size="small"
                    />
                  </Stack>
                </Box>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ xs: 'stretch', md: 'center' }}>
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={hideApprovedPayments}
                        onChange={(e) => setHideApprovedPayments(e.target.checked)}
                        size="small"
                      />
                    }
                    label="Ocultar aprovados"
                    sx={{ m: 0 }}
                  />
                  <Button
                    variant="contained"
                    color="warning"
                    onClick={handleChargeDebtors}
                    disabled={chargingDebtors || paymentDebtors.length === 0}
                    startIcon={<Box component="span" aria-hidden="true">📢</Box>}
                    sx={{ whiteSpace: 'nowrap' }}
                  >
                    {chargingDebtors ? 'Enviando...' : 'Cobrar devedores'}
                  </Button>
                </Stack>
              </Box>
              <Divider />
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Usuário</TableCell>
                    <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>Chave Pix Informada</TableCell>
                    <TableCell align="center">Status</TableCell>
                    <TableCell align="center">
                      <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>Comprovante</Box>
                      <Box component="span" sx={{ display: { xs: 'inline', sm: 'none' } }}>Comp.</Box>
                    </TableCell>
                    <TableCell align="center">Ações</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {visiblePaymentUsers.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                        {hideApprovedPayments ? 'Nenhum pagamento pendente para exibir.' : 'Nenhum usuário cadastrado no sistema.'}
                      </TableCell>
                    </TableRow>
                  ) : (
                    visiblePaymentUsers.map(u => (
                      <TableRow key={u.id}>
                        <TableCell>
                          <Typography
                            variant="body2"
                            sx={{
                              fontWeight: 600,
                              maxWidth: { xs: 96, sm: 'none' },
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap'
                            }}
                          >
                            {u.display_name}
                          </Typography>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{
                              display: 'block',
                              maxWidth: { xs: 96, sm: 'none' },
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap'
                            }}
                          >
                            @{u.username}
                          </Typography>
                        </TableCell>
                        <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>
                          <Typography variant="body2">{u.pix_key_receive || '-'}</Typography>
                        </TableCell>
                        <TableCell align="center">
                          <Box sx={{ display: { xs: 'inline-flex', sm: 'none' }, alignItems: 'center' }}>
                            <Tooltip title={u.payment_status === 'approved' ? 'Pagamento aprovado' : 'Pagamento pendente'}>
                              {u.payment_status === 'approved' ? (
                                <CheckIcon color="success" fontSize="small" />
                              ) : (
                                <PendingPaymentIcon color="warning" fontSize="small" />
                              )}
                            </Tooltip>
                          </Box>
                          <Box sx={{ display: { xs: 'none', sm: 'block' } }}>
                            {u.payment_status === 'approved' && <Chip label="Aprovado" color="success" size="small" />}
                            {u.payment_status === 'submitted' && <Chip label="Aguardando" color="warning" size="small" />}
                            {u.payment_status === 'rejected' && <Chip label="Recusado" color="error" size="small" />}
                            {u.payment_status === 'pending' && <Chip label="Pendente" variant="outlined" size="small" />}
                          </Box>
                        </TableCell>
                        <TableCell align="center">
                          {u.payment_proof_filename ? (
                            <>
                              <Tooltip title="Ver comprovante">
                                <IconButton
                                  size="small"
                                  color="primary"
                                  onClick={() => handleViewPaymentProof(u.id)}
                                  aria-label={`Ver comprovante de ${u.display_name}`}
                                  sx={{ display: { xs: 'inline-flex', sm: 'none' } }}
                                >
                                  <ProofIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>
                              <Button
                                size="small"
                                variant="text"
                                onClick={() => handleViewPaymentProof(u.id)}
                                sx={{ display: { xs: 'none', sm: 'inline-flex' }, fontSize: '0.85rem', textTransform: 'none' }}
                              >
                                Ver Comprovante
                              </Button>
                            </>
                          ) : (
                            <>
                              <Tooltip title="Comprovante não enviado">
                                <CloseIcon color="error" fontSize="small" sx={{ display: { xs: 'inline-flex', sm: 'none' } }} />
                              </Tooltip>
                              <Typography variant="caption" color="text.secondary" sx={{ display: { xs: 'none', sm: 'inline' } }}>
                                Não enviado
                              </Typography>
                            </>
                          )}
                        </TableCell>
                        <TableCell align="center">
                          <Stack direction="row" spacing={0.5} justifyContent="center">
                            <Tooltip title="Aprovar pagamento">
                              <span>
                                <IconButton
                                  size="small"
                                  color="success"
                                  disabled={u.payment_status === 'approved'}
                                  onClick={() => handleApprovePayment(u.id)}
                                  aria-label={`Aprovar pagamento de ${u.display_name}`}
                                >
                                  <CheckIcon fontSize="small" />
                                </IconButton>
                              </span>
                            </Tooltip>
                            <Tooltip title="Reverter aprovação">
                              <span>
                                <IconButton
                                  size="small"
                                  color="warning"
                                  disabled={u.payment_status !== 'approved'}
                                  onClick={() => setRevertPaymentTarget(u)}
                                  aria-label={`Reverter aprovação de pagamento de ${u.display_name}`}
                                >
                                  <RevertIcon fontSize="small" />
                                </IconButton>
                              </span>
                            </Tooltip>
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

      {tabIndex === 'invitations' && user?.role === 'system_admin' && (
        <Stack spacing={3}>
          <Card>
            <CardContent sx={{ p: 4 }}>
              <Stack spacing={2}>
                <Box>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 700, fontFamily: 'Outfit' }}>
                    Link oculto para cadastro direto
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Cadastros feitos por este link entram ativos por padrão. O acesso pode ser desativado em Usuários & Acessos.
                  </Typography>
                </Box>
                <TextField
                  label="Link oculto"
                  value={getHiddenRegistrationUrl()}
                  fullWidth
                  InputProps={{ readOnly: true }}
                  sx={{ '& input': { fontSize: '0.85rem' } }}
                />
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                  <Button
                    variant="contained"
                    onClick={handleCopyHiddenRegistrationLink}
                    disabled={!hiddenRegistrationLink}
                  >
                    Copiar Link
                  </Button>
                  <Button
                    variant="outlined"
                    color="warning"
                    onClick={handleRotateHiddenRegistrationLink}
                    disabled={!hiddenRegistrationLink}
                  >
                    Gerar Novo Link
                  </Button>
                </Stack>
              </Stack>
            </CardContent>
          </Card>

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
	                        <TableCell sx={{ fontWeight: 'bold' }}>Link único</TableCell>
	                        <TableCell sx={{ fontWeight: 'bold' }}>Status</TableCell>
	                        <TableCell sx={{ fontWeight: 'bold' }}>Criado em</TableCell>
	                        <TableCell sx={{ fontWeight: 'bold' }}>Usado em</TableCell>
	                        <TableCell sx={{ fontWeight: 'bold' }} align="center">Ações</TableCell>
	                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {invitationsList.map((inv) => (
                        <TableRow key={inv.id} hover>
	                          <TableCell>{inv.email}</TableCell>
	                          <TableCell>
	                            <Link
	                              href={`${window.location.origin}/register?code=${inv.code}`}
	                              target="_blank"
	                              rel="noopener"
	                              sx={{ fontSize: '0.85rem', wordBreak: 'break-all' }}
	                            >
	                              {`${window.location.origin}/register?code=${inv.code}`}
	                            </Link>
	                          </TableCell>
	                          <TableCell>
	                            {inv.is_used ? (
	                              <Chip label="Usado" color="success" size="small" sx={{ fontWeight: 600 }} />
                            ) : (
                              <Chip label="Pendente" color="warning" size="small" sx={{ fontWeight: 600 }} />
                            )}
	                          </TableCell>
	                          <TableCell>{new Date(inv.created_at).toLocaleString()}</TableCell>
	                          <TableCell>{inv.used_at ? new Date(inv.used_at).toLocaleString() : '-'}</TableCell>
	                          <TableCell align="center">
	                            <Stack direction="row" spacing={1} justifyContent="center">
	                              <Button
	                                size="small"
	                                variant="outlined"
	                                disabled={inv.is_used}
	                                onClick={() => handleResendInvitation(inv)}
	                              >
	                                Reenviar
	                              </Button>
	                              <Button
	                                size="small"
	                                variant="outlined"
	                                color="error"
	                                onClick={() => handleDeleteInvitation(inv)}
	                              >
	                                Excluir
	                              </Button>
	                            </Stack>
	                          </TableCell>
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

      <Dialog open={Boolean(revertPaymentTarget)} onClose={() => setRevertPaymentTarget(null)}>
        <DialogTitle sx={{ fontFamily: 'Outfit', fontWeight: 'bold' }}>Reverter Aprovação de Pagamento</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1, minWidth: { xs: 260, sm: 360 } }}>
            <Alert severity="warning" sx={{ borderRadius: 2 }}>
              Os palpites deste participante voltarão a ficar bloqueados até nova aprovação de pagamento.
            </Alert>
            <Typography variant="body2" color="text.secondary">
              Reverter a aprovação de pagamento de <strong>{revertPaymentTarget?.display_name}</strong>?
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRevertPaymentTarget(null)}>Cancelar</Button>
          <Button onClick={handleConfirmRevertPaymentApproval} variant="contained" color="warning">Reverter Aprovação</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={deleteUserDialogOpen} onClose={() => setDeleteUserDialogOpen(false)}>
        <DialogTitle sx={{ fontFamily: 'Outfit', fontWeight: 'bold' }}>Remover Usuário</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1, minWidth: 360 }}>
            <Alert severity="warning" sx={{ borderRadius: 2 }}>
              Esta ação remove o usuário e seus dados relacionados, como palpites e participação em grupos.
            </Alert>
            <Typography variant="body2" color="text.secondary">
              Confirme a remoção de <strong>{deleteUserTarget?.display_name}</strong> (@{deleteUserTarget?.username}).
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteUserDialogOpen(false)}>Cancelar</Button>
          <Button onClick={handleConfirmDeleteUser} variant="contained" color="error">Remover Usuário</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={confirmDialog.open} onClose={() => setConfirmDialog(prev => ({ ...prev, open: false }))}>
        <DialogTitle sx={{ fontFamily: 'Outfit', fontWeight: 'bold' }}>{confirmDialog.title}</DialogTitle>
        <DialogContent>
          <Typography>{confirmDialog.message}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDialog(prev => ({ ...prev, open: false }))}>Cancelar</Button>
          <Button onClick={confirmDialog.onConfirm} color="primary" variant="contained">
            Confirmar
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
