import React, { useState, useEffect } from 'react'
import {
  Box, Card, CardContent, Typography, Tabs, Tab, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, MenuItem, Select, FormControl, InputLabel,
  Avatar, Alert, Skeleton, Grid, Tooltip
} from '@mui/material'
import {
  EmojiEvents as TrophyIcon,
  Search as SearchIcon,
  HelpOutline
} from '@mui/icons-material'
import axios from 'axios'
import { useAuth } from '../App'

export default function Rankings() {
  const { user } = useAuth()
  
  // Tabs: 0 = General, 1 = By Stage, 2 = By Date
  const [tabIndex, setTabIndex] = useState(0)
  
  // Filters list
  const [stages, setStages] = useState([])
  const [dates, setDates] = useState([])
  const [selectedStage, setSelectedStage] = useState('')
  const [selectedDate, setSelectedDate] = useState('')
  
  // Standings data
  const [rankingData, setRankingData] = useState([])
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
      
      if (tabIndex === 1 && selectedStage) {
        endpoint = `/api/rankings/stage?stage=${encodeURIComponent(selectedStage)}`
      } else if (tabIndex === 2 && selectedDate) {
        endpoint = `/api/rankings/date?date=${selectedDate}`
      }
      
      const res = await axios.get(endpoint)
      setRankingData(res.data)
    } catch (err) {
      setError('Erro ao carregar classificação. Tente novamente mais tarde.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadFilterOptions()
  }, [])

  useEffect(() => {
    loadRanking()
  }, [tabIndex, selectedStage, selectedDate])

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

  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 3 }}>
        🏆 Tabela de Classificação
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>{error}</Alert>}

      {/* Tabs Selector */}
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

      {/* Filters Area depending on Tab */}
      {tabIndex === 1 && (
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

      {tabIndex === 2 && (
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
                  <TableCell align="center"><Skeleton variant="text" /></TableCell>
                </TableRow>
              ))
            ) : rankingData.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} align="center" sx={{ py: 6, color: 'text.secondary' }}>
                  Nenhum usuário classificado para esta visualização.
                </TableCell>
              </TableRow>
            ) : (
              rankingData.map((row, index) => {
                const isMe = row.user_id === user?.id
                const medal = getMedal(row.user_id, row.exact_scores_count)
                return (
                  <TableRow 
                    key={row.user_id}
                    sx={{
                      bgcolor: isMe ? 'rgba(16, 185, 129, 0.05)' : 'transparent',
                      borderLeft: isMe ? '4px solid #10b981' : 'none',
                      '&:hover': { bgcolor: isMe ? 'rgba(16, 185, 129, 0.08)' : 'rgba(255, 255, 255, 0.01)' }
                    }}
                  >
                    {/* Position */}
                    <TableCell align="center" sx={{ fontWeight: 800 }}>
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
                      ) : `${row.position}º`}
                    </TableCell>

                    {/* Avatar & Display Name */}
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
                          <Tooltip title={`Desempates: ${row.exact_scores_count} placar(es) exato(s), ${row.correct_results_count} resultado(s) correto(s), ${row.knockout_points || 0} ponto(s) no mata-mata, ${row.missing_predictions_count} palpite(s) faltante(s) em jogos bloqueados. Palpites registrados: ${row.predictions_count}.`}>
                            <HelpOutline sx={{ fontSize: '0.95rem', cursor: 'help', color: 'text.secondary' }} />
                          </Tooltip>
                        </Box>
                      </Box>
                    </TableCell>

                    {/* Total Points */}
                    <TableCell align="center" sx={{ fontWeight: 800, color: 'primary.light', fontSize: '1.05rem' }}>
                      {row.total_points}
                    </TableCell>

                    {/* Exact count */}
                    <TableCell align="center" sx={{ fontWeight: 600 }}>
                      {row.exact_scores_count}
                    </TableCell>

                    {/* Correct result count */}
                    <TableCell align="center">
                      {row.correct_results_count}
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>

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
