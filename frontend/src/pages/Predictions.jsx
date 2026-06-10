import React, { useState, useEffect, useRef } from 'react'
import {
  Box, Card, CardContent, Typography, Grid, MenuItem, Select, FormControl,
  InputLabel, FormControlLabel, Checkbox, Button, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, TextField, IconButton, Alert, Tooltip, Stack, Chip, Tabs, Tab,
  Dialog, DialogTitle, DialogContent, DialogActions, Divider
} from '@mui/material'
import {
  Lock as LockIcon,
  Save as SaveIcon,
  CheckCircle as CheckIcon,
  HourglassEmpty as PendingIcon,
  ErrorOutline as WarningIcon,
  Article as ReportIcon
} from '@mui/icons-material'
import axios from 'axios'
import { useAuth } from '../App'
import ExportElementImageButton from '../components/ExportElementImageButton'
import GroupStandingsTable from '../components/GroupStandingsTable'
import { getFlagUrl } from '../utils/flags'
import { getGroupStandings, getActualScore, getPredictionScore } from '../utils/standings'
import glivaIcon from '../assets/gliva2.png'

const getFlagUrlLegacy = (emoji) => {
  if (!emoji || emoji === '🏳️') return null

  // Handle exceptions for England and Scotland flags (subnational entities)
  if (
    emoji === '🏴󠁧󠁢󠁥󠁮󠁧󠁿' ||
    emoji === '\u{1F3F4}\u{E0067}\u{E0062}\u{E0065}\u{E006E}\u{E0067}\u{E007F}' ||
    emoji === 'ENG' ||
    emoji === 'England' ||
    emoji === 'Inglaterra'
  ) {
    return 'https://flagcdn.com/w40/gb-eng.png'
  }
  if (
    emoji === '🏴󠁧󠁢󠁳󠁣󠁴󠁿' ||
    emoji === '\u{1F3F4}\u{E0067}\u{E0062}\u{E0073}\u{E0063}\u{E0074}\u{E007F}' ||
    emoji === 'SCO' ||
    emoji === 'Scotland' ||
    emoji === 'Escócia'
  ) {
    return 'https://flagcdn.com/w40/gb-sct.png'
  }

  const codePoints = Array.from(emoji).map(char => char.codePointAt(0))
  if (codePoints.length >= 2 && codePoints[0] >= 127462 && codePoints[0] <= 127487) {
    const char1 = String.fromCharCode(codePoints[0] - 127397)
    const char2 = String.fromCharCode(codePoints[1] - 127397)
    const countryCode = (char1 + char2).toLowerCase()
    return `https://flagcdn.com/w40/${countryCode}.png`
  }
  return null
}

const formatGroupName = (groupName) => {
  if (!groupName) return ''
  return groupName.toLowerCase().startsWith('group ') ? groupName.replace(/^group\s+/i, '') : groupName
}

const LUCKY_SCORE_DISTRIBUTION = [
  { value: 4, weight: 28 },
  { value: 3, weight: 24 },
  { value: 5, weight: 18 },
  { value: 2, weight: 12 },
  { value: 6, weight: 8 },
  { value: 1, weight: 5 },
  { value: 7, weight: 2.5 },
  { value: 0, weight: 1.5 },
  { value: 8, weight: 0.7 },
  { value: 9, weight: 0.3 }
]

const getWeightedLuckyScore = () => {
  const totalWeight = LUCKY_SCORE_DISTRIBUTION.reduce((sum, item) => sum + item.weight, 0)
  let pick = Math.random() * totalWeight
  for (const item of LUCKY_SCORE_DISTRIBUTION) {
    pick -= item.weight
    if (pick <= 0) return item.value
  }
  return 0
}

export default function Predictions() {
  const { user } = useAuth()
  const groupComparisonRef = useRef(null)
  
  // Data lists
  const [matches, setMatches] = useState([])
  const [predictions, setPredictions] = useState({}) // match_id -> prediction
  
  // Grouping and Pagination State
  const [groupingMode, setGroupingMode] = useState('date') // 'date' | 'group'
  const [currentPageIndex, setCurrentPageIndex] = useState(0)

  // Filters within active page
  const [showMissingOnly, setShowMissingOnly] = useState(false)
  const [showLockingSoon, setShowLockingSoon] = useState(false)
  
  // UI states
  const [saveStates, setSaveStates] = useState({}) // match_id -> 'saved' | 'saving' | 'error' | 'unsaved'
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [predictionLockHours, setPredictionLockHours] = useState(3)
  const [predictionListOpen, setPredictionListOpen] = useState(false)
  const [predictionListMatch, setPredictionListMatch] = useState(null)
  const [predictionListData, setPredictionListData] = useState(null)
  const [predictionListLoading, setPredictionListLoading] = useState(false)
  const [predictionListError, setPredictionListError] = useState('')
  const [luckyRolling, setLuckyRolling] = useState({})

  const parseApiDateTime = (value) => {
    if (!value) return new Date(NaN)
    const text = String(value)
    const hasExplicitTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(text)
    return new Date(hasExplicitTimezone ? text : `${text}Z`)
  }

  const autoSelectPage = (loadedMatches, mode) => {
    if (!loadedMatches || loadedMatches.length === 0) return;

    // Find the first match that is not finished
    const nextMatch = loadedMatches.find(m => m.status !== 'finished' && m.status !== 'score_confirmed');
    
    if (!nextMatch) {
      // If all matches are completed, go to the last page
      if (mode === 'date') {
        const sortedDates = [...new Set(loadedMatches.map(m => m.date))].sort();
        const datePagesCount = Math.ceil(sortedDates.length / 3);
        setCurrentPageIndex(Math.max(0, datePagesCount - 1));
      } else {
        const groupsInMatches = [...new Set(loadedMatches.filter(m => m.group_name).map(m => m.group_name))].sort();
        const knockoutStagesInMatches = [...new Set(loadedMatches.filter(m => !m.group_name).map(m => m.stage))];
        const groupPagesCount = groupsInMatches.length + knockoutStagesInMatches.length;
        setCurrentPageIndex(Math.max(0, groupPagesCount - 1));
      }
      return;
    }

    if (mode === 'date') {
      const sortedDates = [...new Set(loadedMatches.map(m => m.date))].sort();
      const matchDateIdx = sortedDates.indexOf(nextMatch.date);
      if (matchDateIdx !== -1) {
        const pageIdx = Math.floor(matchDateIdx / 3);
        setCurrentPageIndex(pageIdx);
      }
    } else {
      const groupsInMatches = [...new Set(loadedMatches.filter(m => m.group_name).map(m => m.group_name))].sort();
      const knockoutStagesInMatches = [...new Set(loadedMatches.filter(m => !m.group_name).map(m => m.stage))];
      
      let pageIdx = -1;
      if (nextMatch.group_name) {
        pageIdx = groupsInMatches.indexOf(nextMatch.group_name);
      } else {
        const stageIdx = knockoutStagesInMatches.indexOf(nextMatch.stage);
        if (stageIdx !== -1) {
          pageIdx = groupsInMatches.length + stageIdx;
        }
      }

      if (pageIdx !== -1) {
        setCurrentPageIndex(pageIdx);
      }
    }
  };

  const handleGroupingModeChange = (newMode) => {
    setGroupingMode(newMode);
    autoSelectPage(matches, newMode);
  };

  const loadData = async () => {
    try {
      setLoading(true)
      
      const settingsRes = await axios.get('/api/predictions/settings')
      setPredictionLockHours(settingsRes.data.prediction_lock_hours ?? 3)

      // Load matches
      const matchesRes = await axios.get('/api/matches')
      const loadedMatches = matchesRes.data;
      setMatches(loadedMatches)

      // Load user predictions
      const predsRes = await axios.get('/api/predictions/my-predictions')
      const predsMap = {}
      predsRes.data.forEach(p => {
        predsMap[p.match_id] = p
      })
      setPredictions(predsMap)

      // Auto-select page on load
      autoSelectPage(loadedMatches, groupingMode)
    } catch (err) {
      setError('Erro ao carregar os dados das partidas. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // Auto-save function triggered on blur
  const handleAutoSave = async (matchId, goals1, goals2, qualName) => {
    // Both goals must be defined (non-empty)
    if (goals1 === undefined || goals2 === undefined || goals1 === '' || goals2 === '') {
      return
    }

    setSaveStates(prev => ({ ...prev, [matchId]: 'saving' }))
    try {
      const res = await axios.post(`/api/predictions/save?match_id=${matchId}`, {
        goals_team1: parseInt(goals1),
        goals_team2: parseInt(goals2),
        qualified_team_name: qualName || null
      })
      
      // Update local predictions map
      setPredictions(prev => ({
        ...prev,
        [matchId]: res.data
      }))
      setSaveStates(prev => ({ ...prev, [matchId]: 'saved' }))
      
      // Reset saved indicator after 3 seconds
      setTimeout(() => {
        setSaveStates(prev => {
          if (prev[matchId] === 'saved') {
            const next = { ...prev }
            delete next[matchId]
            return next
          }
          return prev
        })
      }, 3000)
    } catch (err) {
      setSaveStates(prev => ({ ...prev, [matchId]: 'error' }))
    }
  }

  const handleInputChange = (matchId, field, value) => {
    // Only permit non-negative integers
    if (value !== '' && !/^\d+$/.test(value)) return
    
    // Check if match is locked (client safety)
    const match = matches.find(m => m.id === matchId)
    if (match && isLocked(match.kickoff_time)) {
      return
    }

    const currentPred = predictions[matchId] || {}
    const updatedPred = {
      ...currentPred,
      [field]: value
    }

    setPredictions(prev => ({
      ...prev,
      [matchId]: {
        ...prev[matchId],
        [field]: value
      }
    }))
    setSaveStates(prev => ({ ...prev, [matchId]: 'unsaved' }))

    // Trigger auto-save if both fields are filled (not empty)
    if (updatedPred.goals_team1 !== undefined && updatedPred.goals_team2 !== undefined &&
        updatedPred.goals_team1 !== '' && updatedPred.goals_team2 !== '') {
      handleAutoSave(matchId, updatedPred.goals_team1, updatedPred.goals_team2, updatedPred.qualified_team_name)
    }
  }

  const handleLuckyPrediction = (match) => {
    if (!match || luckyRolling[match.id] || isLocked(match.kickoff_time)) return
    if (user?.role === 'system_admin' || user?.role === 'score_admin' || user?.payment_status !== 'approved') return

    const finalGoals1 = getWeightedLuckyScore()
    const finalGoals2 = getWeightedLuckyScore()
    const currentPred = predictions[match.id] || {}

    setLuckyRolling(prev => ({ ...prev, [match.id]: true }))
    setSaveStates(prev => ({ ...prev, [match.id]: 'unsaved' }))

    const intervalId = window.setInterval(() => {
      setPredictions(prev => ({
        ...prev,
        [match.id]: {
          ...prev[match.id],
          goals_team1: Math.floor(Math.random() * 10),
          goals_team2: Math.floor(Math.random() * 10)
        }
      }))
    }, 80)

    window.setTimeout(() => {
      window.clearInterval(intervalId)
      setPredictions(prev => ({
        ...prev,
        [match.id]: {
          ...prev[match.id],
          goals_team1: finalGoals1,
          goals_team2: finalGoals2,
          qualified_team_name: currentPred.qualified_team_name || null
        }
      }))
      setLuckyRolling(prev => {
        const next = { ...prev }
        delete next[match.id]
        return next
      })
      handleAutoSave(match.id, finalGoals1, finalGoals2, currentPred.qualified_team_name)
    }, 1000)
  }

  const renderLuckyButton = (match, locked) => (
    <Tooltip title="Pergunte ao Gliva">
      <span>
        <IconButton
          size="small"
          color="secondary"
          onClick={() => handleLuckyPrediction(match)}
          disabled={
            locked ||
            Boolean(luckyRolling[match.id]) ||
            user?.role === 'system_admin' ||
            user?.role === 'score_admin' ||
            user?.payment_status !== 'approved'
          }
          aria-label="Pergunte ao Gliva"
          sx={{ width: 40, height: 40 }}
        >
          <Box
            component="img"
            src={glivaIcon}
            alt=""
            aria-hidden="true"
            sx={{
              width: 32,
              height: 32,
              objectFit: 'contain'
            }}
          />
        </IconButton>
      </span>
    </Tooltip>
  )

  const isLocked = (kickoffTimeIso) => {
    const now = new Date()
    const kickoff = parseApiDateTime(kickoffTimeIso)
    const lockTime = new Date(kickoff.getTime() - predictionLockHours * 60 * 60 * 1000)
    return now >= lockTime
  }

  const isLockingSoon = (kickoffTimeIso) => {
    const now = new Date()
    const kickoff = parseApiDateTime(kickoffTimeIso)
    const lockTime = new Date(kickoff.getTime() - predictionLockHours * 60 * 60 * 1000)
    const warningTime = new Date(now.getTime() + 24 * 60 * 60 * 1000) // 24 hours warning
    return now < lockTime && lockTime <= warningTime
  }

  const handleOpenPredictionList = async (match) => {
    setPredictionListMatch(match)
    setPredictionListOpen(true)
    setPredictionListData(null)
    setPredictionListError('')
    setPredictionListLoading(true)

    try {
      const res = await axios.get(`/api/predictions/match/${match.id}/visibility`)
      setPredictionListData(res.data)
    } catch (err) {
      setPredictionListError('Não foi possível carregar a lista de palpites desta partida.')
    } finally {
      setPredictionListLoading(false)
    }
  }

  const handleClosePredictionList = () => {
    setPredictionListOpen(false)
    setPredictionListMatch(null)
    setPredictionListData(null)
    setPredictionListError('')
  }

  const renderPredictionListButton = (match, locked) => (
    <Tooltip title={locked ? 'Ver palpites realizados neste jogo' : 'Ver quem já palpitou neste jogo'}>
      <IconButton
        size="small"
        color="primary"
        onClick={() => handleOpenPredictionList(match)}
        aria-label={locked ? 'Ver palpites realizados neste jogo' : 'Ver quem já palpitou neste jogo'}
      >
        <ReportIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  )

  const formatDateTime = (isoString) => {
    const d = parseApiDateTime(isoString)
    const weekday = d.toLocaleDateString('pt-BR', { weekday: 'short', timeZone: 'America/Sao_Paulo' })
    const date = d.toLocaleDateString('pt-BR', { day: 'numeric', month: 'numeric', timeZone: 'America/Sao_Paulo' })
    const time = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Sao_Paulo' })
    return `${weekday.toUpperCase()}, ${date} - ${time}`
  }

  // ==========================================
  // Pagination Data Calculations
  // ==========================================
  
  // 1. Date-based chunks (3 days)
  const sortedDates = [...new Set(matches.map(m => m.date))].sort()
  const datePages = []
  for (let i = 0; i < sortedDates.length; i += 3) {
    datePages.push(sortedDates.slice(i, i + 3))
  }

  // 2. Group & Stage chunks
  const groupsInMatches = [...new Set(matches.filter(m => m.group_name).map(m => m.group_name))].sort()
  const knockoutStagesInMatches = [...new Set(matches.filter(m => !m.group_name).map(m => m.stage))]
  const groupPages = [
    ...groupsInMatches.map(g => ({ type: 'group', value: g, label: `Grupo ${formatGroupName(g)}` })),
    ...knockoutStagesInMatches.map(s => {
      let label = s;
      if (s === 'Round of 32') label = '16-avos';
      else if (s === 'Round of 16') label = 'Oitavas';
      else if (s === 'Quarter-finals') label = 'Quartas';
      else if (s === 'Semi-finals') label = 'Semifinais';
      else if (s === 'Final') label = 'Finais';
      return { type: 'stage', value: s, label };
    })
  ]

  const totalPages = groupingMode === 'date' ? datePages.length : groupPages.length
  const safePageIndex = currentPageIndex >= totalPages ? 0 : currentPageIndex

  // Filter matches for the current active page
  const activeMatchesOnPage = matches.filter(match => {
    let onPage = false
    if (groupingMode === 'date') {
      const activeDates = datePages[safePageIndex] || []
      onPage = activeDates.includes(match.date)
    } else {
      const activePage = groupPages[safePageIndex]
      if (activePage) {
        if (activePage.type === 'group') {
          onPage = match.group_name === activePage.value
        } else {
          onPage = match.stage === activePage.value && !match.group_name
        }
      }
    }
    if (!onPage) return false

    // Apply secondary filters
    const pred = predictions[match.id]
    const hasPred = pred && pred.goals_team1 !== undefined && pred.goals_team2 !== undefined && pred.goals_team1 !== '' && pred.goals_team2 !== ''
    
    if (showMissingOnly) {
      if (isLocked(match.kickoff_time)) return false
      if (hasPred) return false
    }
    if (showLockingSoon) {
      if (!isLockingSoon(match.kickoff_time)) return false
    }
    return true
  })

  const activeGroupPage = groupingMode === 'group' ? groupPages[safePageIndex] : null
  const activeGroupName = activeGroupPage?.type === 'group' ? activeGroupPage.value : null
  const expectationGroup = activeGroupName ? getGroupStandings(matches, activeGroupName, getPredictionScore(predictions)) : null
  const realityGroup = activeGroupName ? getGroupStandings(matches, activeGroupName, getActualScore) : null
  const groupComparisonFileName = activeGroupName
    ? `expectativa_realidade_grupo_${formatGroupName(activeGroupName)
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-zA-Z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .toLowerCase() || 'grupo'}.png`
    : 'expectativa_realidade_grupo.png'

  const renderGroupComparison = () => {
    if (!activeGroupName || !expectationGroup || !realityGroup) return null

    return (
      <Box sx={{ mt: 3 }}>
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: { xs: 'stretch', sm: 'center' },
            flexDirection: { xs: 'column', sm: 'row' },
            gap: 1.5,
            mb: 2
          }}
        >
          <Typography variant="h6" sx={{ fontWeight: 800, fontFamily: 'Outfit' }}>
            Grupo {formatGroupName(activeGroupName)}: Expectativa x Realidade
          </Typography>
          <ExportElementImageButton
            targetRef={groupComparisonRef}
            fileName={groupComparisonFileName}
            shareTitle={`Grupo ${formatGroupName(activeGroupName)} - Expectativa x Realidade`}
            label="Compartilhar Comparativo"
            size="small"
          />
        </Box>

        <Box ref={groupComparisonRef} sx={{ bgcolor: 'background.default', p: { xs: 1.5, sm: 2 }, borderRadius: 2 }}>
          <Typography variant="h6" sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 2 }}>
            Grupo {formatGroupName(activeGroupName)}: Expectativa x Realidade
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent sx={{ p: 2 }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 800, mb: 1 }}>
                    Expectativa
                  </Typography>
                  <GroupStandingsTable standings={expectationGroup.standings} dense />
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent sx={{ p: 2 }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 800, mb: 1 }}>
                    Realidade
                  </Typography>
                  <GroupStandingsTable standings={realityGroup.standings} dense />
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Box>
      </Box>
    )
  }

  const predictionPointGroups = predictionListData?.is_scored
    ? Object.values((predictionListData.entries || []).reduce((groups, entry) => {
        const points = Number(entry.points_earned || 0)
        if (!groups[points]) {
          groups[points] = { points, entries: [] }
        }
        groups[points].entries.push(entry)
        return groups
      }, {})).sort((a, b) => b.points - a.points)
    : []

  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 3, display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <Box component="img" src="/icons/icon-192.png" alt="Logo" sx={{ width: 36, height: 36 }} />
        Registro de Palpites
      </Typography>

      {user?.role !== 'system_admin' && user?.role !== 'score_admin' && user?.payment_status !== 'approved' && (
        <Alert severity="warning" sx={{ mb: 3, borderRadius: 3, fontWeight: 600 }}>
          ⚠️ Acesso Bloqueado: Para poder registrar e editar palpites, você precisa ter seu pagamento aprovado pelo administrador. 
          Acesse a página de <a href="/profile" style={{ color: '#fff', textDecoration: 'underline', fontWeight: 'bold' }}>seu Perfil</a> para enviar seu comprovante.
        </Alert>
      )}

      {error && <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>{error}</Alert>}

      {/* Filters Card */}
      <Card sx={{ mb: 4 }}>
        <CardContent sx={{ p: 3 }}>
          <Box sx={{ 
            display: 'flex', 
            flexDirection: { xs: 'column', md: 'row' },
            justifyContent: 'space-between', 
            alignItems: { xs: 'stretch', md: 'center' }, 
            gap: 2 
          }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ xs: 'flex-start', sm: 'center' }} gap={1}>
              <Typography variant="body2" sx={{ fontWeight: 700, color: 'text.secondary' }}>Agrupar por:</Typography>
              <Box display="flex" gap={1} flexWrap="wrap">
                <Chip 
                  label="🗓️ Datas (3 dias)" 
                  clickable 
                  color={groupingMode === 'date' ? 'primary' : 'default'} 
                  variant={groupingMode === 'date' ? 'filled' : 'outlined'} 
                  onClick={() => handleGroupingModeChange('date')} 
                  size="small"
                />
                <Chip 
                  label="🏆 Grupos & Fases" 
                  clickable 
                  color={groupingMode === 'group' ? 'primary' : 'default'} 
                  variant={groupingMode === 'group' ? 'filled' : 'outlined'} 
                  onClick={() => handleGroupingModeChange('group')} 
                  size="small"
                />
              </Box>
            </Stack>

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 1, sm: 2 }} alignItems="flex-start" flexWrap="wrap">
              <FormControlLabel
                control={
                  <Checkbox
                    checked={showMissingOnly}
                    onChange={(e) => {
                      setShowMissingOnly(e.target.checked)
                      if (e.target.checked) setShowLockingSoon(false)
                    }}
                    color="primary"
                    size="small"
                  />
                }
                label="Apenas palpites faltantes"
                componentsProps={{ typography: { variant: 'body2', fontWeight: 600 } }}
                sx={{ mr: 0 }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={showLockingSoon}
                    onChange={(e) => {
                      setShowLockingSoon(e.target.checked)
                      if (e.target.checked) setShowMissingOnly(false)
                    }}
                    color="primary"
                    size="small"
                  />
                }
                label="Bloqueando em 24h"
                componentsProps={{ typography: { variant: 'body2', fontWeight: 600 } }}
                sx={{ mr: 0 }}
              />
            </Stack>
          </Box>
        </CardContent>
      </Card>

      {/* Pagination Tabs Bar */}
      {totalPages > 0 && (
        <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 4, width: '100%', overflow: 'hidden' }}>
          <Tabs 
            value={safePageIndex} 
            onChange={(e, val) => setCurrentPageIndex(val)} 
            variant="scrollable" 
            scrollButtons="auto"
            sx={{
              '& .MuiTab-root': {
                fontFamily: 'Outfit',
                fontWeight: 700,
                fontSize: '0.9rem',
                textTransform: 'none',
                minWidth: 100,
              }
            }}
          >
            {groupingMode === 'date' ? (
              datePages.map((dates, idx) => {
                const start = new Date(dates[0] + 'T00:00:00');
                const end = new Date(dates[dates.length - 1] + 'T00:00:00');
                const label = `${start.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })} a ${end.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}`;
                return <Tab key={idx} label={label} />;
              })
            ) : (
              groupPages.map((page, idx) => (
                <Tab key={idx} label={page.label} />
              ))
            )}
          </Tabs>
        </Box>
      )}

      {/* Desktop Table View */}
      <Box sx={{ display: { xs: 'none', md: 'block' } }}>
        <TableContainer component={Paper} sx={{ borderRadius: 3, boxShadow: '0 4px 20px rgba(0,0,0,0.15)' }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Fase / Estádio</TableCell>
                <TableCell>Horário (SP)</TableCell>
                <TableCell align="right" sx={{ width: '25%' }}>Time A</TableCell>
                <TableCell align="center" sx={{ width: '18%' }}>Palpite</TableCell>
                <TableCell align="left" sx={{ width: '25%' }}>Time B</TableCell>
                <TableCell align="center">Resultado / Pontuação</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={6} align="center" sx={{ py: 6 }}>
                    Carregando partidas...
                  </TableCell>
                </TableRow>
              ) : activeMatchesOnPage.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} align="center" sx={{ py: 6, color: 'text.secondary' }}>
                    Nenhuma partida encontrada nesta página para os filtros selecionados.
                  </TableCell>
                </TableRow>
              ) : (
                activeMatchesOnPage.map((match) => {
                  const locked = isLocked(match.kickoff_time);
                  const soon = isLockingSoon(match.kickoff_time);
                  const pred = predictions[match.id] || {};
                  const goals1 = pred.goals_team1 ?? '';
                  const goals2 = pred.goals_team2 ?? '';
                  const saveState = saveStates[match.id];
                  
                  const isFinished = match.status === 'finished' || match.status === 'score_confirmed';

                  return (
                    <TableRow 
                      key={match.id}
                      sx={{
                        bgcolor: soon && !locked ? 'rgba(245, 158, 11, 0.02)' : isFinished ? 'rgba(255, 255, 255, 0.005)' : 'transparent',
                        '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.01)' }
                      }}
                    >
                      {/* Stage & Stadium */}
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {match.round}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          📍 {match.ground}
                        </Typography>
                        <Box sx={{ mt: 0.5 }}>
                          {renderPredictionListButton(match, locked)}
                        </Box>
                      </TableCell>

                      {/* Date/Time */}
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 500 }}>
                          {formatDateTime(match.kickoff_time)}
                        </Typography>
                        {soon && !locked && (
                          <Typography variant="caption" color="warning.main" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5, fontWeight: 'bold' }}>
                            <WarningIcon fontSize="inherit" /> Bloqueia em breve
                          </Typography>
                        )}
                        {locked && !isFinished && (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5, fontWeight: 'bold' }}>
                            <LockIcon fontSize="inherit" /> Bloqueado
                          </Typography>
                        )}
                        {isFinished && (
                          <Chip 
                            label="Encerrado" 
                            size="small" 
                            variant="outlined" 
                            sx={{ height: 16, fontSize: '0.6rem', color: 'text.secondary', borderColor: 'divider', mt: 0.5 }} 
                          />
                        )}
                      </TableCell>

                      {/* Team A */}
                      <TableCell align="right" sx={{ fontWeight: 700, fontSize: '1rem' }}>
                        <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 1 }}>
                          {getFlagUrl(match.team1?.flag_icon, match.team1) ? (
                            <img src={getFlagUrl(match.team1.flag_icon, match.team1)} alt="" style={{ width: 20, height: 14, borderRadius: 1.5, objectFit: 'cover' }} />
                          ) : (
                            <span>{match.team1?.flag_icon}</span>
                          )}
                          {match.team1_name}
                        </Box>
                      </TableCell>

                      {/* Prediction column */}
                      <TableCell align="center">
                        {locked ? (
                          goals1 !== '' && goals2 !== '' ? (
                            <Chip 
                              label={`${goals1} x ${goals2}`} 
                              color="primary" 
                              variant="outlined" 
                              sx={{ fontWeight: 'bold', fontFamily: 'Outfit', fontSize: '1rem', px: 1 }} 
                            />
                          ) : (
                            <Chip 
                              label="Sem palpite" 
                              color="error" 
                              variant="outlined" 
                              size="small" 
                              sx={{ fontSize: '0.8rem' }} 
                            />
                          )
                        ) : (
                          <Stack direction="column" spacing={1} alignItems="center">
                            <Box display="flex" alignItems="center" justifyContent="center" gap={1.5}>
                              <TextField
                                size="small"
                                disabled={locked || Boolean(luckyRolling[match.id]) || (user?.role !== 'system_admin' && user?.role !== 'score_admin' && user?.payment_status !== 'approved')}
                                sx={{ width: 55 }}
                                inputProps={{ min: 0, style: { textAlign: 'center', fontWeight: 'bold', fontSize: '1.1rem' } }}
                                value={goals1}
                                onChange={(e) => handleInputChange(match.id, 'goals_team1', e.target.value)}
                                onBlur={() => handleAutoSave(match.id, goals1, goals2, pred.qualified_team_name)}
                              />
                              <Typography variant="body2" sx={{ fontWeight: 'bold', color: 'text.secondary' }}>x</Typography>
                              <TextField
                                size="small"
                                disabled={locked || Boolean(luckyRolling[match.id]) || (user?.role !== 'system_admin' && user?.role !== 'score_admin' && user?.payment_status !== 'approved')}
                                sx={{ width: 55 }}
                                inputProps={{ min: 0, style: { textAlign: 'center', fontWeight: 'bold', fontSize: '1.1rem' } }}
                                value={goals2}
                                onChange={(e) => handleInputChange(match.id, 'goals_team2', e.target.value)}
                                onBlur={() => handleAutoSave(match.id, goals1, goals2, pred.qualified_team_name)}
                              />
                              {renderLuckyButton(match, locked)}
                            </Box>
                          </Stack>
                        )}
                      </TableCell>

                      {/* Team B */}
                      <TableCell align="left" sx={{ fontWeight: 700, fontSize: '1rem' }}>
                        <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 1 }}>
                          {match.team2_name}
                          {getFlagUrl(match.team2?.flag_icon, match.team2) ? (
                            <img src={getFlagUrl(match.team2.flag_icon, match.team2)} alt="" style={{ width: 20, height: 14, borderRadius: 1.5, objectFit: 'cover' }} />
                          ) : (
                            <span>{match.team2?.flag_icon}</span>
                          )}
                        </Box>
                      </TableCell>

                      {/* Status / Results column */}
                      <TableCell align="center">
                        {isFinished ? (
                          <Box sx={{ py: 0.5 }}>
                            <Typography variant="caption" sx={{ display: 'block', fontWeight: 800, color: 'text.primary', mb: 0.5 }}>
                              Resultado: {match.score_ft_team1} x {match.score_ft_team2}
                            </Typography>
                            {pred.points_earned !== undefined && pred.points_earned !== null ? (
                              <Chip 
                                label={`+${pred.points_earned} pts`} 
                                color={pred.points_earned > 0 ? 'success' : 'default'} 
                                size="small" 
                                sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 0.5 }} 
                              />
                            ) : (
                              <Chip 
                                label="0 pts" 
                                size="small" 
                                sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 0.5 }} 
                              />
                            )}
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontSize: '0.65rem', maxWidth: 150, mx: 'auto', lineHeight: 1.1 }}>
                              {pred.scoring_explanation}
                            </Typography>
                          </Box>
                        ) : locked ? (
                          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                            Jogo em andamento
                          </Typography>
                        ) : (
                          <Box>
                            {saveState === 'saving' && <Typography variant="caption" color="text.secondary">Salvando...</Typography>}
                            {saveState === 'saved' && (
                              <Typography variant="caption" color="primary.main" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'center' }}>
                                <CheckIcon fontSize="inherit" /> Salvo
                              </Typography>
                            )}
                            {saveState === 'error' && <Typography variant="caption" color="error.main">Erro ao salvar</Typography>}
                            {saveState === 'unsaved' && <Typography variant="caption" color="warning.main">Não salvo</Typography>}
                            {!saveState && goals1 !== '' && goals2 !== '' && (
                              <Typography variant="caption" color="text.secondary">Salvo</Typography>
                            )}
                            {!saveState && (goals1 === '' || goals2 === '') && (
                              <Typography variant="caption" color="error.main">Sem palpite</Typography>
                            )}
                          </Box>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>

      {/* Mobile Stacked Card View */}
      <Box sx={{ display: { xs: 'block', md: 'none' } }}>
        {loading ? (
          <Alert severity="info" sx={{ borderRadius: 2 }}>Carregando palpites...</Alert>
        ) : activeMatchesOnPage.length === 0 ? (
          <Alert severity="info" sx={{ borderRadius: 2 }}>
            Nenhuma partida encontrada nesta página para os filtros selecionados.
          </Alert>
        ) : (
          <Stack spacing={2}>
            {activeMatchesOnPage.map((match) => {
              const locked = isLocked(match.kickoff_time);
              const soon = isLockingSoon(match.kickoff_time);
              const pred = predictions[match.id] || {};
              const goals1 = pred.goals_team1 ?? '';
              const goals2 = pred.goals_team2 ?? '';
              const saveState = saveStates[match.id];
              const isFinished = match.status === 'finished' || match.status === 'score_confirmed';

              return (
                <Card 
                  key={match.id} 
                  sx={{ 
                    borderRadius: 3, 
                    border: '1px solid',
                    borderColor: soon && !locked ? 'warning.main' : 'divider',
                    bgcolor: isFinished ? 'rgba(255,255,255,0.005)' : 'background.default',
                    overflow: 'visible'
                  }}
                >
                  <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                    {/* Header info */}
                    <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
                      <Box>
                        <Typography variant="caption" sx={{ fontWeight: 700, color: 'text.secondary', display: 'block' }}>
                          {match.round} • {match.ground.split('(')[0].trim()}
                        </Typography>
                        <Typography variant="caption" sx={{ fontWeight: 600, color: soon && !locked ? 'warning.main' : 'primary.main' }}>
                          {formatDateTime(match.kickoff_time)}
                        </Typography>
                      </Box>
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        {renderPredictionListButton(match, locked)}
                        {soon && !locked && (
                          <Chip label="Bloqueia logo" color="warning" size="small" sx={{ fontSize: '0.65rem', height: 18 }} />
                        )}
                        {locked && !isFinished && (
                          <Chip icon={<LockIcon sx={{ fontSize: '0.8rem !important' }} />} label="Bloqueado" size="small" variant="outlined" sx={{ fontSize: '0.65rem', height: 18 }} />
                        )}
                        {isFinished && (
                          <Chip label="Encerrado" size="small" color="default" variant="outlined" sx={{ fontSize: '0.65rem', height: 18, color: 'text.secondary', borderColor: 'divider' }} />
                        )}
                      </Stack>
                    </Box>

                    {/* Match Row */}
                    <Box display="flex" alignItems="center" justifyContent="space-between" sx={{ gap: 0.5, mb: 1.5 }}>
                      {/* Symmetrical placeholder to keep inputs centered */}
                      {!locked && <Box sx={{ width: 40, flexShrink: 0 }} />}

                      {/* Team A */}
                      <Box display="flex" alignItems="center" gap={0.5} sx={{ flex: 1, minWidth: 0, justifyContent: 'flex-end' }}>
                        <Typography variant="body2" sx={{ fontWeight: 800, textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {match.team1?.fifa_code || match.team1_name}
                        </Typography>
                        {getFlagUrl(match.team1?.flag_icon, match.team1) ? (
                          <img src={getFlagUrl(match.team1.flag_icon, match.team1)} alt="" style={{ width: 20, height: 14, borderRadius: 1, flexShrink: 0 }} />
                        ) : (
                          <span style={{ fontSize: '1rem', flexShrink: 0 }}>{match.team1?.flag_icon}</span>
                        )}
                      </Box>

                      {/* Guess display or inputs */}
                      {locked ? (
                        <Box sx={{ flexShrink: 0 }}>
                          {goals1 !== '' && goals2 !== '' ? (
                            <Chip 
                              label={`${goals1} x ${goals2}`} 
                              color="primary" 
                              variant="outlined" 
                              size="small"
                              sx={{ fontWeight: 'bold', fontFamily: 'Outfit' }} 
                            />
                          ) : (
                            <Chip 
                              label="Sem palpite" 
                              color="error" 
                              variant="outlined" 
                              size="small" 
                            />
                          )}
                        </Box>
                      ) : (
                        <Box display="flex" alignItems="center" gap={0.5} sx={{ flexShrink: 0, px: 0.5 }}>
                          <TextField
                            size="small"
                            disabled={locked || Boolean(luckyRolling[match.id]) || (user?.role !== 'system_admin' && user?.role !== 'score_admin' && user?.payment_status !== 'approved')}
                            sx={{ width: 45 }}
                            inputProps={{ min: 0, style: { textAlign: 'center', fontWeight: 'bold', fontSize: '1rem' } }}
                            value={goals1}
                            onChange={(e) => handleInputChange(match.id, 'goals_team1', e.target.value)}
                            onBlur={() => handleAutoSave(match.id, goals1, goals2, pred.qualified_team_name)}
                          />
                          <Typography variant="caption" sx={{ fontWeight: 'bold', color: 'text.secondary' }}>x</Typography>
                          <TextField
                            size="small"
                            disabled={locked || Boolean(luckyRolling[match.id]) || (user?.role !== 'system_admin' && user?.role !== 'score_admin' && user?.payment_status !== 'approved')}
                            sx={{ width: 45 }}
                            inputProps={{ min: 0, style: { textAlign: 'center', fontWeight: 'bold', fontSize: '1rem' } }}
                            value={goals2}
                            onChange={(e) => handleInputChange(match.id, 'goals_team2', e.target.value)}
                            onBlur={() => handleAutoSave(match.id, goals1, goals2, pred.qualified_team_name)}
                          />
                        </Box>
                      )}

                      {/* Team B */}
                      <Box display="flex" alignItems="center" gap={0.5} sx={{ flex: 1, minWidth: 0, justifyContent: 'flex-start' }}>
                        {getFlagUrl(match.team2?.flag_icon, match.team2) ? (
                          <img src={getFlagUrl(match.team2.flag_icon, match.team2)} alt="" style={{ width: 20, height: 14, borderRadius: 1, flexShrink: 0 }} />
                        ) : (
                          <span style={{ fontSize: '1rem', flexShrink: 0 }}>{match.team2?.flag_icon}</span>
                        )}
                        <Typography variant="body2" sx={{ fontWeight: 800, textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {match.team2?.fifa_code || match.team2_name}
                        </Typography>
                      </Box>

                      {/* Gliva Button */}
                      {!locked && (
                        <Box sx={{ flexShrink: 0 }}>
                          {renderLuckyButton(match, locked)}
                        </Box>
                      )}
                    </Box>

                    {/* Result and points row */}
                    <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ pt: 1, borderTop: '1px solid #1f2937' }}>
                      {/* Explanatory text / status */}
                      <Box sx={{ flexGrow: 1, pr: 1 }}>
                        {isFinished && (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontSize: '0.65rem', lineHeight: 1.1 }}>
                            {pred.scoring_explanation}
                          </Typography>
                        )}
                      </Box>

                      {/* Outcome display */}
                      <Box sx={{ textAlign: 'right' }}>
                        {isFinished ? (
                          <Box>
                            <Typography variant="caption" sx={{ display: 'block', fontWeight: 'bold', color: 'text.primary', mb: 0.5 }}>
                              Resultado: {match.score_ft_team1} x {match.score_ft_team2}
                            </Typography>
                            {pred.points_earned !== undefined && pred.points_earned !== null ? (
                              <Chip 
                                label={`+${pred.points_earned} pts`} 
                                color={pred.points_earned > 0 ? 'success' : 'default'} 
                                size="small" 
                                sx={{ fontWeight: 800, fontFamily: 'Outfit' }} 
                              />
                            ) : (
                              <Chip 
                                label="0 pts" 
                                size="small" 
                                sx={{ fontWeight: 800, fontFamily: 'Outfit' }} 
                              />
                            )}
                          </Box>
                        ) : locked ? (
                          <Typography variant="caption" color="text.secondary">Jogo em andamento</Typography>
                        ) : (
                          <Box>
                            {saveState === 'saving' && <Typography variant="caption" color="text.secondary">Salvando...</Typography>}
                            {saveState === 'saved' && <Typography variant="caption" color="primary.main">Salvo</Typography>}
                            {saveState === 'error' && <Typography variant="caption" color="error.main">Erro</Typography>}
                            {saveState === 'unsaved' && <Typography variant="caption" color="warning.main">Não salvo</Typography>}
                            {!saveState && goals1 !== '' && goals2 !== '' && (
                              <Typography variant="caption" color="text.secondary">Salvo</Typography>
                            )}
                            {!saveState && (goals1 === '' || goals2 === '') && (
                              <Typography variant="caption" color="error.main">Sem palpite</Typography>
                            )}
                          </Box>
                        )}
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              );
            })}
          </Stack>
        )}
      </Box>

      {renderGroupComparison()}

      <Dialog open={predictionListOpen} onClose={handleClosePredictionList} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontFamily: 'Outfit', fontWeight: 800 }}>
          Participantes que já palpitaram ({predictionListData?.total_predictions ?? 0}/{predictionListData?.total_participants ?? '-'})
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {predictionListMatch && (
              <Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                  {predictionListMatch.team1_name} x {predictionListMatch.team2_name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {formatDateTime(predictionListMatch.kickoff_time)}
                </Typography>
              </Box>
            )}

            {predictionListLoading && (
              <Alert severity="info" sx={{ borderRadius: 2 }}>
                Carregando lista...
              </Alert>
            )}

            {predictionListError && (
              <Alert severity="error" sx={{ borderRadius: 2 }}>
                {predictionListError}
              </Alert>
            )}

            {predictionListData && !predictionListLoading && !predictionListError && (
              predictionListData.entries.length === 0 ? (
                <Alert severity="info" sx={{ borderRadius: 2 }}>
                  Nenhum participante registrou palpite para este jogo ainda.
                </Alert>
              ) : predictionListData.is_scored ? (
                <Stack spacing={2}>
                  <Box>
                    <Typography variant="subtitle2" sx={{ fontWeight: 800, mb: 1 }}>
                      Distribuição de pontos
                    </Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ rowGap: 1 }}>
                      {(predictionListData.points_summary || []).map(item => (
                        <Chip
                          key={item.points}
                          label={`${item.count} ${item.count === 1 ? 'pessoa' : 'pessoas'} com ${item.points} pts`}
                          color={item.points > 0 ? 'success' : 'default'}
                          variant={item.points > 0 ? 'filled' : 'outlined'}
                          size="small"
                          sx={{ fontWeight: 800 }}
                        />
                      ))}
                    </Stack>
                  </Box>

                  {predictionPointGroups.map(group => (
                    <Box key={group.points}>
                      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                        <Chip
                          label={`${group.points} pts`}
                          color={group.points > 0 ? 'primary' : 'default'}
                          size="small"
                          sx={{ fontWeight: 900, fontFamily: 'Outfit' }}
                        />
                        <Typography variant="caption" color="text.secondary">
                          {group.entries.length} {group.entries.length === 1 ? 'palpiteiro' : 'palpiteiros'}
                        </Typography>
                      </Stack>
                      <TableContainer component={Paper} sx={{ boxShadow: 'none', border: '1px solid', borderColor: 'divider' }}>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>Participante</TableCell>
                              <TableCell align="center">Palpite</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {group.entries.map(entry => (
                              <TableRow key={entry.user_id}>
                                <TableCell>
                                  <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                    {entry.display_name}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    Enviado em {formatDateTime(entry.created_at)}
                                  </Typography>
                                </TableCell>
                                <TableCell align="center">
                                  <Chip
                                    label={`${entry.goals_team1} x ${entry.goals_team2}`}
                                    color="primary"
                                    variant="outlined"
                                    size="small"
                                    sx={{ fontWeight: 800, fontFamily: 'Outfit' }}
                                  />
                                  {entry.qualified_team_name && (
                                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                                      Classifica: {entry.qualified_team_name}
                                    </Typography>
                                  )}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                      {group !== predictionPointGroups[predictionPointGroups.length - 1] && <Divider sx={{ mt: 2 }} />}
                    </Box>
                  ))}
                </Stack>
              ) : (
                <TableContainer component={Paper} sx={{ boxShadow: 'none' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Participante</TableCell>
                        {predictionListData.is_locked && <TableCell align="center">Palpite</TableCell>}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {predictionListData.entries.map(entry => (
                        <TableRow key={entry.user_id}>
                          <TableCell>
                            <Typography variant="body2" sx={{ fontWeight: 700 }}>
                              {entry.display_name}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              Enviado em {formatDateTime(entry.created_at)}
                            </Typography>
                          </TableCell>
                          {predictionListData.is_locked && (
                            <TableCell align="center">
                              <Chip
                                label={`${entry.goals_team1} x ${entry.goals_team2}`}
                                color="primary"
                                variant="outlined"
                                size="small"
                                sx={{ fontWeight: 800, fontFamily: 'Outfit' }}
                              />
                              {entry.qualified_team_name && (
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                                  Classifica: {entry.qualified_team_name}
                                </Typography>
                              )}
                            </TableCell>
                          )}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClosePredictionList}>Fechar</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
