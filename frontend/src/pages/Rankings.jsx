import React, { useState, useEffect, useRef } from 'react'
import {
  Box, Card, CardContent, Typography, Tabs, Tab, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, MenuItem, Select, FormControl, InputLabel,
  Avatar, Alert, Skeleton, Grid, Tooltip, Checkbox, FormControlLabel, Stack
} from '@mui/material'
import {
  EmojiEvents as TrophyIcon,
  Search as SearchIcon,
  HelpOutline,
  ArrowUpward,
  ArrowDownward
} from '@mui/icons-material'
import axios from 'axios'
import { useAuth } from '../App'
import ExportElementImageButton from '../components/ExportElementImageButton'
import lucidoIcon from '../assets/lucido.png'

export default function Rankings() {
  const { user } = useAuth()
  const generalTop10Ref = useRef(null)
  const lucidoTop10Ref = useRef(null)
  const [rankingType, setRankingType] = useState('normal') // 'normal' | 'lucido'
  
  // Tabs: 0 = General, 1 = By Stage, 2 = By Date
  const [tabIndex, setTabIndex] = useState(0)
  
  // Filters list
  const [stages, setStages] = useState([])
  const [dates, setDates] = useState([])
  const [selectedStage, setSelectedStage] = useState('')
  const [selectedDate, setSelectedDate] = useState('')
  
  // Standings data
  const [rankingData, setRankingData] = useState([])
  const [rankingHistory, setRankingHistory] = useState({ dates: [], participants: [] })
  const [selectedChartUsers, setSelectedChartUsers] = useState({})
  const [historyLoading, setHistoryLoading] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadFilterOptions = async () => {
    try {
      const matchesRes = await axios.get('/api/matches')
      const stagesSet = new Set(matchesRes.data.map(m => m.stage))
      const datesSet = new Set(matchesRes.data.map(m => m.date))
      
      const stList = Array.from(stagesSet)
      const dtList = Array.from(datesSet).sort()
      
      setStages(stList)
      setDates(dtList)
      
      if (stList.length > 0) setSelectedStage(stList[0])
      if (dtList.length > 0) setSelectedDate(dtList[0])
    } catch (err) {
      console.error('Erro ao carregar filtros do ranking:', err)
    }
  }

  const loadRanking = async () => {
    try {
      setLoading(true)
      setError('')
      let endpoint = '/api/rankings/general'
      
      if (rankingType === 'lucido') {
        endpoint = '/api/rankings/lucido/general'
      } else {
        if (tabIndex === 1 && selectedStage) {
          endpoint = `/api/rankings/stage?stage=${encodeURIComponent(selectedStage)}`
        } else if (tabIndex === 2 && selectedDate) {
          endpoint = `/api/rankings/date?date=${selectedDate}`
        }
      }
      
      const res = await axios.get(endpoint)
      setRankingData(res.data)
    } catch (err) {
      setError('Erro ao carregar classificação. Tente novamente mais tarde.')
    } finally {
      setLoading(false)
    }
  }

  const loadRankingHistory = async () => {
    try {
      setHistoryLoading(true)
      const res = await axios.get('/api/rankings/history')
      setRankingHistory(res.data)
      setSelectedChartUsers(prev => {
        const hasSelection = Object.keys(prev).length > 0
        if (hasSelection) {
          const next = {}
          res.data.participants.forEach(participant => {
            next[participant.user_id] = prev[participant.user_id] ?? false
          })
          return next
        }

        const initial = {}
        res.data.participants.forEach(participant => {
          initial[participant.user_id] = Boolean(participant.is_default_visible)
        })
        return initial
      })
    } catch (err) {
      setRankingHistory({ dates: [], participants: [] })
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    loadFilterOptions()
    loadRankingHistory()
  }, [])

  useEffect(() => {
    loadRanking()
  }, [tabIndex, selectedStage, selectedDate, rankingType])

  const handleTabChange = (event, newIndex) => {
    setTabIndex(newIndex)
  }

  // Determine top 3 exact score hit medal winners
  const medalWinners = [...rankingData].sort((a, b) => {
    if (b.exact_scores_count !== a.exact_scores_count) {
      return b.exact_scores_count - a.exact_scores_count
    }
    return rankingData.indexOf(a) - rankingData.indexOf(b)
  })

  const getMedal = (userId, exactCount) => {
    if (!exactCount || exactCount === 0) return null
    const idx = medalWinners.findIndex(w => w.user_id === userId)
    if (idx === 0) return { src: '/ouro.png', label: 'Ouro' }
    if (idx === 1) return { src: '/prata.png', label: 'Prata' }
    if (idx === 2) return { src: '/bronze.png', label: 'Bronze' }
    return null
  }

  const getMovementIndicator = (positionChange) => {
    if (!positionChange) return null
    const gained = positionChange > 0
    const amount = Math.abs(positionChange)
    return {
      amount,
      color: gained ? '#22c55e' : '#ef4444',
      icon: gained ? <ArrowUpward sx={{ fontSize: 15 }} /> : <ArrowDownward sx={{ fontSize: 15 }} />,
      label: gained
        ? `Ganhou ${amount} posição${amount === 1 ? '' : 'ões'} desde o último ranking`
        : `Perdeu ${amount} posição${amount === 1 ? '' : 'ões'} desde o último ranking`
    }
  }

  const renderPosition = (row, movement) => (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 0.75 }}>
      {row.position === 1 ? (
        <Typography sx={{ color: 'secondary.main', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5, fontWeight: 900 }}>
          🥇 1º
        </Typography>
      ) : row.position === 2 ? (
        <Typography sx={{ color: 'text.primary', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5, fontWeight: 900 }}>
          🥈 2º
        </Typography>
      ) : row.position === 3 ? (
        <Typography sx={{ color: '#cd7f32', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5, fontWeight: 900 }}>
          🥉 3º
        </Typography>
      ) : (
        <Typography sx={{ fontWeight: 900 }}>{row.position}º</Typography>
      )}
      {movement && (
        <Tooltip title={movement.label}>
          <Box sx={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 0.15,
            color: movement.color,
            fontSize: '0.78rem',
            fontWeight: 900,
            lineHeight: 1
          }}>
            {movement.icon}
            {movement.amount}
          </Box>
        </Tooltip>
      )}
    </Box>
  )

  const renderRankingRows = (rows, { showTieBreakerHelp = true } = {}) => (
    rows.map((row) => {
      const isMe = row.user_id === user?.id
      const medal = getMedal(row.user_id, row.exact_scores_count)
      const movement = getMovementIndicator(row.position_change)
      return (
        <TableRow
          key={row.user_id}
          sx={{
            bgcolor: isMe ? 'rgba(16, 185, 129, 0.05)' : 'transparent',
            borderLeft: isMe ? '4px solid #10b981' : 'none',
            '&:hover': { bgcolor: isMe ? 'rgba(16, 185, 129, 0.08)' : 'rgba(255, 255, 255, 0.01)' }
          }}
        >
          <TableCell align="center" sx={{ fontWeight: 800 }}>
            {renderPosition(row, movement)}
          </TableCell>

          <TableCell>
            <Box display="flex" alignItems="center" gap={2}>
              <Avatar
                src={row.avatar_url || ''}
                alt={row.display_name}
                sx={{ width: 32, height: 32, bgcolor: isMe ? 'primary.main' : '#374151', fontSize: '0.85rem', fontWeight: 'bold' }}
              >
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
                        height: 20,
                        width: 20,
                        objectFit: 'contain',
                        cursor: 'pointer',
                        transition: 'transform 0.2s',
                        '&:hover': { transform: 'scale(1.25)' }
                      }}
                    />
                  </Tooltip>
                )}
                <Typography sx={{ fontWeight: isMe ? 700 : 500 }}>
                  {row.display_name} {isMe && '(Você)'}
                </Typography>
                {showTieBreakerHelp && (
                  <Tooltip title={`Desempates: ${row.exact_scores_count} placar(es) exato(s), ${row.correct_results_count - row.exact_scores_count} apenas resultado(s) (vencedor/empate), ${row.knockout_points || 0} ponto(s) no mata-mata, ${row.missing_predictions_count} palpite(s) faltante(s) em jogos bloqueados. Palpites registrados: ${row.predictions_count}.`}>
                    <HelpOutline sx={{ fontSize: '0.95rem', cursor: 'help', color: 'text.secondary' }} />
                  </Tooltip>
                )}
              </Box>
            </Box>
          </TableCell>

          <TableCell align="center" sx={{ fontWeight: 800, color: 'primary.light', fontSize: '1.05rem' }}>
            {row.total_points}
          </TableCell>

          <TableCell align="center" sx={{ fontWeight: 600 }}>
            {row.exact_scores_count}
          </TableCell>

          <TableCell align="center">
            {row.correct_results_count - row.exact_scores_count}
          </TableCell>
        </TableRow>
      )
    })
  )

  const renderLucidoRankingRows = (rows, { isExport = false } = {}) => (
    rows.map((row) => {
      const isMe = row.user_id === user?.id
      return (
        <TableRow
          key={row.user_id}
          sx={{
            bgcolor: isMe ? 'rgba(16, 185, 129, 0.05)' : 'transparent',
            borderLeft: isMe ? '4px solid #10b981' : 'none',
            '&:hover': { bgcolor: isMe ? 'rgba(16, 185, 129, 0.08)' : 'rgba(255, 255, 255, 0.01)' }
          }}
        >
          <TableCell align="center" sx={{ fontWeight: 800 }}>
            {row.position === 1 ? (
              <Typography sx={{ color: 'secondary.main', fontWeight: 900, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
                🤡 1º
              </Typography>
            ) : row.position === 2 ? (
              <Typography sx={{ color: 'text.primary', fontWeight: 900, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
                🥈 2º
              </Typography>
            ) : row.position === 3 ? (
              <Typography sx={{ color: '#cd7f32', fontWeight: 900, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
                🥉 3º
              </Typography>
            ) : (
              <Typography sx={{ fontWeight: 900 }}>{row.position}º</Typography>
            )}
          </TableCell>

          <TableCell>
            <Box display="flex" alignItems="center" gap={2}>
              <Avatar
                src={row.avatar_url || ''}
                alt={row.display_name}
                sx={{ width: 32, height: 32, bgcolor: isMe ? 'primary.main' : '#374151', fontSize: '0.85rem', fontWeight: 'bold' }}
              >
                {row.display_name.charAt(0).toUpperCase()}
              </Avatar>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                {row.position <= 3 && (
                  <Tooltip title={`Top 3 Palpitador Lúcido (${row.position}º lugar)`}>
                    <Box
                      component="img"
                      src={lucidoIcon}
                      alt="Lúcido"
                      sx={{
                        height: 22,
                        width: 22,
                        objectFit: 'contain',
                        cursor: 'pointer',
                        transition: 'transform 0.2s',
                        '&:hover': { transform: 'scale(1.25)' }
                      }}
                    />
                  </Tooltip>
                )}
                <Typography sx={{ fontWeight: isMe ? 700 : 500 }}>
                  {row.display_name} {isMe && '(Você)'}
                </Typography>
              </Box>
            </Box>
          </TableCell>

          <TableCell align="center" sx={{ fontWeight: 800, color: 'warning.light', fontSize: '1.05rem' }}>
            {row.zero_points_count}
          </TableCell>

          <TableCell align="center" sx={{ fontWeight: 600, color: 'text.secondary' }}>
            {row.total_goal_difference}
          </TableCell>
        </TableRow>
      )
    })
  )

  const chartParticipants = rankingHistory.participants.filter(participant => selectedChartUsers[participant.user_id])
  const maxChartPosition = Math.max(
    1,
    ...rankingHistory.participants.flatMap(participant => participant.snapshots.map(snapshot => snapshot.position))
  )
  const chartColors = ['#10b981', '#f59e0b', '#60a5fa', '#f472b6', '#a78bfa', '#f87171', '#34d399', '#facc15', '#38bdf8', '#fb7185']

  const getChartColor = (index) => chartColors[index % chartColors.length]

  const formatChartDate = (date) => {
    const parsed = new Date(`${date}T00:00:00`)
    return parsed.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
  }

  const getParticipantPath = (participant, width, height, padding) => {
    if (!rankingHistory.dates.length || !participant.snapshots.length) return ''
    const snapshotByDate = Object.fromEntries(participant.snapshots.map(snapshot => [snapshot.date, snapshot]))
    const points = rankingHistory.dates
      .map((date, index) => {
        const snapshot = snapshotByDate[date]
        if (!snapshot) return null
        const x = rankingHistory.dates.length === 1
          ? width / 2
          : padding.left + (index / (rankingHistory.dates.length - 1)) * (width - padding.left - padding.right)
        const y = padding.top + ((snapshot.position - 1) / Math.max(1, maxChartPosition - 1)) * (height - padding.top - padding.bottom)
        return { x, y, snapshot, date }
      })
      .filter(Boolean)

    return points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')
  }

  const getParticipantPoints = (participant, width, height, padding) => {
    const snapshotByDate = Object.fromEntries(participant.snapshots.map(snapshot => [snapshot.date, snapshot]))
    return rankingHistory.dates
      .map((date, index) => {
        const snapshot = snapshotByDate[date]
        if (!snapshot) return null
        const x = rankingHistory.dates.length === 1
          ? width / 2
          : padding.left + (index / (rankingHistory.dates.length - 1)) * (width - padding.left - padding.right)
        const y = padding.top + ((snapshot.position - 1) / Math.max(1, maxChartPosition - 1)) * (height - padding.top - padding.bottom)
        return { x, y, snapshot, date }
      })
      .filter(Boolean)
  }

  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 3 }}>
        🏆 Tabela de Classificação
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>{error}</Alert>}

      {/* Top level toggle tabs for Normal vs Lucido */}
      <Tabs 
        value={rankingType} 
        onChange={(e, val) => setRankingType(val)}
        textColor="secondary"
        indicatorColor="secondary"
        sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}
      >
        <Tab label="Classificação Geral" value="normal" sx={{ fontWeight: 'bold', fontFamily: 'Outfit' }} />
        <Tab label="Prêmio Lúcido 🤡" value="lucido" sx={{ fontWeight: 'bold', fontFamily: 'Outfit' }} />
      </Tabs>

      {/* Export Button */}
      {rankingData.length > 0 && !loading && (
        <Box sx={{ display: 'flex', justifyContent: { xs: 'stretch', sm: 'flex-end' }, mb: 2 }}>
          {rankingType === 'normal' ? (
            tabIndex === 0 && (
              <ExportElementImageButton
                targetRef={generalTop10Ref}
                fileName="ranking_geral_top_10.png"
                shareTitle="Ranking Geral - Top 10"
                label="Compartilhar Top 10"
                fullWidth={false}
              />
            )
          ) : (
            <ExportElementImageButton
              targetRef={lucidoTop10Ref}
              fileName="ranking_premio_lucido_top_10.png"
              shareTitle="Prêmio Lúcido - Top 10"
              label="Compartilhar Top 10"
              fullWidth={false}
            />
          )}
        </Box>
      )}

      {/* Prêmio Lúcido Banner */}
      {rankingType === 'lucido' && (
        <Card sx={{ mb: 3, background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(239, 68, 68, 0.05) 100%)', border: '1px solid rgba(245, 158, 11, 0.2)' }}>
          <CardContent sx={{ p: 3, display: 'flex', alignItems: 'center', gap: 3, flexDirection: { xs: 'column', sm: 'row' } }}>
            <Box
              component="img"
              src={lucidoIcon}
              alt="Prêmio Lúcido"
              sx={{ width: 80, height: 80, objectFit: 'contain' }}
            />
            <Box sx={{ textAlign: { xs: 'center', sm: 'left' } }}>
              <Typography variant="h6" sx={{ fontWeight: 800, fontFamily: 'Outfit', color: 'warning.main', mb: 0.5 }}>
                🤡 Prêmio Lúcido
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 600 }}>
                Homenagem especial para os participantes que mais acumularam palpites com <strong>exatamente 0 pontos</strong> durante o bolão! Apenas palpites enviados e computados são considerados (jogos sem palpite não entram na conta).
              </Typography>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Tabs Selector for Normal view */}
      {rankingType === 'normal' && (
        <Tabs 
          value={tabIndex} 
          onChange={handleTabChange} 
          textColor="primary"
          indicatorColor="primary"
          sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}
        >
          <Tab label="Geral" sx={{ fontWeight: 'bold' }} />
          <Tab label="Por Fase do Torneio" sx={{ fontWeight: 'bold' }} />
          <Tab label="Por Dia (Data)" sx={{ fontWeight: 'bold' }} />
        </Tabs>
      )}

      {/* Filters Area depending on Tab for Normal view */}
      {rankingType === 'normal' && tabIndex === 1 && (
        <Card sx={{ mb: 3 }}>
          <CardContent sx={{ p: 2 }}>
            <FormControl size="small" sx={{ minWidth: 250 }}>
              <InputLabel>Selecionar Fase</InputLabel>
              <Select
                value={selectedStage}
                label="Selecionar Fase"
                onChange={(e) => setSelectedStage(e.target.value)}
              >
                {stages.map(s => (
                  <MenuItem key={s} value={s}>
                    {s === 'Group Stage' ? 'Fase de Grupos' : s}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </CardContent>
        </Card>
      )}

      {rankingType === 'normal' && tabIndex === 2 && (
        <Card sx={{ mb: 3 }}>
          <CardContent sx={{ p: 2 }}>
            <FormControl size="small" sx={{ minWidth: 250 }}>
              <InputLabel>Selecionar Data</InputLabel>
              <Select
                value={selectedDate}
                label="Selecionar Data"
                onChange={(e) => setSelectedDate(e.target.value)}
              >
                {dates.map(d => (
                  <MenuItem key={d} value={d}>
                    {new Date(d + 'T00:00:00').toLocaleDateString('pt-BR', { dateStyle: 'long' })}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </CardContent>
        </Card>
      )}

      {/* Standings Table */}
      <TableContainer component={Paper} sx={{ borderRadius: 3, overflowX: 'auto' }}>
        <Table>
          <TableHead>
            {rankingType === 'normal' ? (
              <TableRow>
                <TableCell align="center" sx={{ width: '8%' }}>Pos</TableCell>
                <TableCell>Participante</TableCell>
                <TableCell align="center">Pts Totais</TableCell>
                <TableCell align="center">
                  <Box display="inline-flex" alignItems="center" gap={0.5}>
                    Placar Exato (10)
                    <Tooltip title="Número de palpites com placar 100% correto (10 pontos)">
                      <HelpOutline sx={{ fontSize: '0.9rem', cursor: 'help', color: 'text.secondary' }} />
                    </Tooltip>
                  </Box>
                </TableCell>
                <TableCell align="center">
                  <Box display="inline-flex" alignItems="center" gap={0.5}>
                    Resultado Certo (3/4/6)
                    <Tooltip title="Número de palpites com vencedor ou empate correto (3, 4 ou 6 pontos)">
                      <HelpOutline sx={{ fontSize: '0.9rem', cursor: 'help', color: 'text.secondary' }} />
                    </Tooltip>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              <TableRow>
                <TableCell align="center" sx={{ width: '8%' }}>Pos</TableCell>
                <TableCell>Participante</TableCell>
                <TableCell align="center">Palpites com 0 Pts</TableCell>
                <TableCell align="center">
                  <Box display="inline-flex" alignItems="center" gap={0.5}>
                    Diferença de Gols
                    <Tooltip title="Soma das diferenças absolutas de gols nos palpites com 0 pontos. Usado como critério de desempate (maior valor vence).">
                      <HelpOutline sx={{ fontSize: '0.9rem', cursor: 'help', color: 'text.secondary' }} />
                    </Tooltip>
                  </Box>
                </TableCell>
              </TableRow>
            )}
          </TableHead>
          <TableBody>
            {loading ? (
              // Loading skeletons
              Array.from(new Array(5)).map((_, idx) => (
                <TableRow key={idx}>
                  <TableCell align="center"><Skeleton variant="text" /></TableCell>
                  <TableCell>
                    <Box display="flex" alignItems="center" gap={2}>
                      <Skeleton variant="circular" width={32} height={32} />
                      <Skeleton variant="text" width={120} />
                    </Box>
                  </TableCell>
                  <TableCell align="center"><Skeleton variant="text" /></TableCell>
                  <TableCell align="center"><Skeleton variant="text" /></TableCell>
                  {rankingType === 'normal' && <TableCell align="center"><Skeleton variant="text" /></TableCell>}
                </TableRow>
              ))
            ) : rankingData.length === 0 ? (
              <TableRow>
                <TableCell colSpan={rankingType === 'normal' ? 5 : 4} align="center" sx={{ py: 6, color: 'text.secondary' }}>
                  Nenhum usuário classificado para esta visualização.
                </TableCell>
              </TableRow>
            ) : rankingType === 'normal' ? (
              renderRankingRows(rankingData)
            ) : (
              renderLucidoRankingRows(rankingData)
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {rankingType === 'normal' && tabIndex === 0 && (
        <Card sx={{ mt: 3, mb: 3 }}>
          <CardContent sx={{ p: { xs: 2, md: 3 } }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, flexDirection: { xs: 'column', md: 'row' }, mb: 2 }}>
              <Box>
                <Typography variant="h6" sx={{ fontWeight: 800, fontFamily: 'Outfit' }}>
                  Evolução da classificação
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Posição geral por snapshot diário. A posição 1 aparece no topo.
                </Typography>
              </Box>
              <Typography variant="caption" color="text.secondary">
                Padrão: você e os 5 primeiros
              </Typography>
            </Box>

            {historyLoading ? (
              <Skeleton variant="rectangular" height={320} sx={{ borderRadius: 2 }} />
            ) : rankingHistory.dates.length === 0 || rankingHistory.participants.length === 0 ? (
              <Alert severity="info" sx={{ borderRadius: 2 }}>
                Ainda não há snapshots de classificação suficientes para montar o histórico.
              </Alert>
            ) : (
              <Grid container spacing={2}>
                <Grid item xs={12} lg={8}>
                  <Box sx={{ overflowX: 'auto', border: '1px solid #1f2937', borderRadius: 2, bgcolor: 'background.default' }}>
                    <Box
                      component="svg"
                      viewBox="0 0 900 340"
                      role="img"
                      aria-label="Gráfico de evolução de posições no ranking"
                      sx={{ display: 'block', minWidth: 720, width: '100%', height: 340 }}
                    >
                      {(() => {
                        const width = 900
                        const height = 340
                        const padding = { top: 28, right: 28, bottom: 54, left: 54 }
                        const chartWidth = width - padding.left - padding.right
                        const chartHeight = height - padding.top - padding.bottom
                        const yTicks = Array.from(
                          new Set([1, Math.ceil(maxChartPosition / 2), maxChartPosition].filter(value => value >= 1))
                        )

                        return (
                          <>
                            <line x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} stroke="#374151" />
                            <line x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} stroke="#374151" />

                            {yTicks.map(position => {
                              const y = padding.top + ((position - 1) / Math.max(1, maxChartPosition - 1)) * chartHeight
                              return (
                                <g key={position}>
                                  <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="#1f2937" strokeDasharray="4 6" />
                                  <text x={padding.left - 10} y={y + 4} textAnchor="end" fill="#9ca3af" fontSize="12">
                                    {position}º
                                  </text>
                                </g>
                              )
                            })}

                            {rankingHistory.dates.map((date, index) => {
                              const x = rankingHistory.dates.length === 1
                                ? width / 2
                                : padding.left + (index / (rankingHistory.dates.length - 1)) * chartWidth
                              return (
                                <g key={date}>
                                  <line x1={x} y1={padding.top} x2={x} y2={height - padding.bottom} stroke="#111827" />
                                  <text x={x} y={height - 20} textAnchor="middle" fill="#9ca3af" fontSize="12">
                                    {formatChartDate(date)}
                                  </text>
                                </g>
                              )
                            })}

                            {chartParticipants.map((participant) => {
                              const color = getChartColor(rankingHistory.participants.findIndex(item => item.user_id === participant.user_id))
                              const points = getParticipantPoints(participant, width, height, padding)
                              return (
                                <g key={participant.user_id}>
                                  <path
                                    d={getParticipantPath(participant, width, height, padding)}
                                    fill="none"
                                    stroke={color}
                                    strokeWidth="2.5"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                  />
                                  {points.map(point => (
                                    <circle
                                      key={`${participant.user_id}-${point.date}`}
                                      cx={point.x}
                                      cy={point.y}
                                      r="4.5"
                                      fill={color}
                                      stroke="#0b0f19"
                                      strokeWidth="2"
                                    >
                                      <title>{`${participant.display_name}: ${point.snapshot.position}º em ${formatChartDate(point.date)} (${point.snapshot.total_points} pts)`}</title>
                                    </circle>
                                  ))}
                                </g>
                              )
                            })}
                          </>
                        )
                      })()}
                    </Box>
                  </Box>
                </Grid>

                <Grid item xs={12} lg={4}>
                  <Box sx={{ maxHeight: 340, overflowY: 'auto', pr: 1 }}>
                    <Stack spacing={0.5}>
                      {rankingHistory.participants.map((participant, index) => (
                        <FormControlLabel
                          key={participant.user_id}
                          control={
                            <Checkbox
                              size="small"
                              checked={Boolean(selectedChartUsers[participant.user_id])}
                              onChange={(event) => {
                                setSelectedChartUsers(prev => ({
                                  ...prev,
                                  [participant.user_id]: event.target.checked
                                }))
                              }}
                              sx={{
                                color: getChartColor(index),
                                '&.Mui-checked': { color: getChartColor(index) }
                              }}
                            />
                          }
                          label={
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              <Avatar src={participant.avatar_url || ''} sx={{ width: 22, height: 22, fontSize: 12 }}>
                                {participant.display_name.charAt(0).toUpperCase()}
                              </Avatar>
                              <Typography variant="body2" noWrap>
                                {participant.display_name}
                                {participant.user_id === user?.id ? ' (você)' : ''}
                              </Typography>
                            </Box>
                          }
                          sx={{ m: 0, minWidth: 0 }}
                        />
                      ))}
                    </Stack>
                  </Box>
                </Grid>
              </Grid>
            )}
          </CardContent>
        </Card>
      )}

      <Box
        sx={{
          position: 'absolute',
          left: -10000,
          top: 0,
          width: 760,
          bgcolor: 'background.paper'
        }}
        aria-hidden="true"
      >
        <Card ref={generalTop10Ref}>
          <CardContent sx={{ p: 3 }}>
            <Typography variant="h6" sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 2 }}>
              🏆 Ranking Geral - Top 10
            </Typography>
            <TableContainer component={Paper} sx={{ boxShadow: 'none', borderRadius: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell align="center" sx={{ width: '8%' }}>Pos</TableCell>
                    <TableCell>Participante</TableCell>
                    <TableCell align="center">Pts Totais</TableCell>
                    <TableCell align="center">Placar Exato</TableCell>
                    <TableCell align="center">Resultado Certo</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {renderRankingRows(rankingData.slice(0, 10), { showTieBreakerHelp: false })}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>

        <Card ref={lucidoTop10Ref} sx={{ mt: 3 }}>
          <CardContent sx={{ p: 3 }}>
            <Box display="flex" alignItems="center" gap={1.5} sx={{ mb: 2 }}>
              <Box component="img" src={lucidoIcon} sx={{ width: 28, height: 28, objectFit: 'contain' }} />
              <Typography variant="h6" sx={{ fontWeight: 800, fontFamily: 'Outfit' }}>
                🤡 Prêmio Lúcido - Top 10
              </Typography>
            </Box>
            <TableContainer component={Paper} sx={{ boxShadow: 'none', borderRadius: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell align="center" sx={{ width: '8%' }}>Pos</TableCell>
                    <TableCell>Participante</TableCell>
                    <TableCell align="center">Palpites com 0 Pts</TableCell>
                    <TableCell align="center">Diferença de Gols</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {renderLucidoRankingRows(rankingData.slice(0, 10), { isExport: true })}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      </Box>

      {/* Tie breaker documentation banner */}
      <Card sx={{ mt: 4, bgcolor: '#111827' }}>
        <CardContent sx={{ p: 3 }}>
          <Typography variant="subtitle2" color="secondary.main" sx={{ fontWeight: 700, mb: 1, fontFamily: 'Outfit' }}>
            ℹ️ Critérios de Desempate (Ordem de Prioridade):
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.6 }}>
            1. Maior pontuação total; <br />
            2. Maior número de palpites com placar exato (10 pontos); <br />
            3. Maior número de palpites com resultado correto (3, 4 ou 6 pontos); <br />
            4. Maior pontuação obtida na fase eliminatória (Mata-mata); <br />
            5. Menor número de palpites faltantes em jogos já bloqueados; <br />
            6. Data/Hora de cadastro mais antiga no sistema; <br />
            7. Ordem alfabética do nome de exibição.
          </Typography>
        </CardContent>
      </Card>
    </Box>
  )
}
