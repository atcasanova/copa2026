import React, { useState, useEffect } from 'react'
import { useNavigate, Link as RouterLink } from 'react-router-dom'
import {
  Box, Grid, Card, CardContent, Typography, Button, Avatar, Stack,
  List, ListItem, ListItemText, ListItemSecondaryAction, Divider, Alert, Badge, TextField
} from '@mui/material'
import {
  TrendingUp as TrendIcon,
  EmojiEvents as TrophyIcon,
  HourglassEmpty as HourglassIcon,
  GroupAdd as GroupInviteIcon,
  NavigateNext as NextIcon,
  CheckCircle as SuccessIcon,
  SportsSoccer as SoccerIcon
} from '@mui/icons-material'
import axios from 'axios'
import AnnouncementBanner from '../components/AnnouncementBanner'
import { useAuth } from '../App'
import { getFlagUrl } from '../utils/flags'

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

export default function Dashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  
  const [stats, setStats] = useState(null)
  const [pendingInvites, setPendingInvites] = useState([])
  const [lockingSoon, setLockingSoon] = useState([])
  const [missingPredictions, setMissingPredictions] = useState([])
  const [upcomingMatches, setUpcomingMatches] = useState([])
  
  // Local state for quick prediction inputs
  const [predGoals, setPredGoals] = useState({})
  const [savedPreds, setSavedPreds] = useState({})
  
  const [loading, setLoading] = useState(true)
  const loadDashboardData = async () => {
    try {
      setLoading(true)
      const settingsRes = await axios.get('/api/predictions/settings').catch(() => ({ data: { prediction_lock_hours: 3 } }))
      const lockHours = settingsRes.data.prediction_lock_hours ?? 3

      await Promise.all([
        axios.get('/api/rankings/me')
          .then(res => setStats(res.data))
          .catch(err => console.error('Erro ao carregar estatísticas:', err)),
        
        axios.get('/api/groups/invitations/pending')
          .then(res => setPendingInvites(res.data))
          .catch(err => console.error('Erro ao carregar convites pendentes:', err)),
        
        axios.get('/api/predictions/locking-soon?hours=48')
          .then(res => setLockingSoon(res.data))
          .catch(err => console.error('Erro ao carregar jogos bloqueando em breve:', err)),
        
        axios.get('/api/predictions/missing')
          .then(res => setMissingPredictions(res.data))
          .catch(err => console.error('Erro ao carregar palpites faltantes:', err)),
        
        axios.get('/api/matches')
          .then(res => {
            const now = new Date()
	            const future = res.data.filter(m => {
	              const kickoff = new Date(m.kickoff_time)
	              const lockTime = new Date(kickoff.getTime() - lockHours * 60 * 60 * 1000)
	              return m.status === 'scheduled' && now < lockTime
	            })
            setUpcomingMatches(future.slice(0, 4))
          })
          .catch(err => console.error('Erro ao carregar próximas partidas:', err)),
        
        axios.get('/api/predictions/my-predictions')
          .then(res => {
            const predsMap = {}
            res.data.forEach(p => {
              predsMap[p.match_id] = {
                goals_team1: p.goals_team1,
                goals_team2: p.goals_team2
              }
            })
            setPredGoals(predsMap)
          })
          .catch(err => console.error('Erro ao carregar meus palpites:', err))
      ])
    } catch (err) {
      console.error('Erro ao carregar dados do dashboard:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDashboardData()
  }, [])

  const executeQuickPredictSave = async (matchId, goals1, goals2) => {
    try {
      await axios.post(`/api/predictions/save?match_id=${matchId}`, {
        goals_team1: parseInt(goals1),
        goals_team2: parseInt(goals2)
      })
      
      // Set saved state indicator
      setSavedPreds(prev => ({ ...prev, [matchId]: true }))
      setTimeout(() => {
        setSavedPreds(prev => ({ ...prev, [matchId]: false }))
      }, 3000)
      
      // Reload stats
      const statsRes = await axios.get('/api/rankings/me')
      setStats(statsRes.data)
      
      // Update missing count
      const missingRes = await axios.get('/api/predictions/missing')
      setMissingPredictions(missingRes.data)
    } catch (err) {
      console.error("Erro ao salvar palpite rápido:", err)
    }
  }

  const handleQuickPredictSave = async (matchId) => {
    const pred = predGoals[matchId]
    if (!pred || pred.goals_team1 === undefined || pred.goals_team2 === undefined || pred.goals_team1 === '' || pred.goals_team2 === '') {
      alert("Por favor, preencha os gols de ambos os times.")
      return
    }
    await executeQuickPredictSave(matchId, pred.goals_team1, pred.goals_team2)
  }

  const handleInputChange = (matchId, teamField, val) => {
    if (val !== '' && !/^\d+$/.test(val)) return // Only numbers
    
    const currentPred = predGoals[matchId] || {}
    const updatedPred = {
      ...currentPred,
      [teamField]: val
    }

    setPredGoals(prev => ({
      ...prev,
      [matchId]: updatedPred
    }))

    // Auto-save if both fields are filled (not empty)
    if (updatedPred.goals_team1 !== undefined && updatedPred.goals_team2 !== undefined &&
        updatedPred.goals_team1 !== '' && updatedPred.goals_team2 !== '') {
      executeQuickPredictSave(matchId, updatedPred.goals_team1, updatedPred.goals_team2)
    }
  }

  const handleInviteResponse = async (inviteId, accept) => {
    try {
      await axios.post(`/api/groups/invitations/${inviteId}/respond?accept=${accept}`)
      loadDashboardData()
    } catch (err) {
      alert('Erro ao responder convite.')
    }
  }

  const formatTime = (isoString) => {
    const d = new Date(isoString)
    return d.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', dateStyle: 'short', timeStyle: 'short' })
  }

  return (
    <Box sx={{ mt: 1 }}>
      {/* Top Banner for Announcements */}
      <AnnouncementBanner onUpdate={loadDashboardData} />

      {/* Grid containing header alerts */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        {/* Total Points */}
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ bgcolor: 'rgba(16, 185, 129, 0.1)', borderColor: 'rgba(16, 185, 129, 0.3)' }}>
            <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Avatar sx={{ bgcolor: 'primary.main', width: 52, height: 52 }}>
                <TrophyIcon />
              </Avatar>
              <Box>
                <Typography variant="body2" color="text.secondary">Pontos Acumulados</Typography>
                <Typography variant="h4" sx={{ fontWeight: 800, fontFamily: 'Outfit' }}>
                  {stats?.general?.total_points || 0}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* General Standing */}
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ bgcolor: 'rgba(251, 191, 36, 0.1)', borderColor: 'rgba(251, 191,  yellow, 0.3)' }}>
            <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Avatar sx={{ bgcolor: 'secondary.main', color: 'secondary.contrastText', width: 52, height: 52 }}>
                <TrendIcon />
              </Avatar>
              <Box>
                <Typography variant="body2" color="text.secondary">Posição Geral</Typography>
                <Typography variant="h4" sx={{ fontWeight: 800, fontFamily: 'Outfit' }}>
                  {stats?.general?.position ? `${stats.general.position}º` : '-'}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Missing Bets */}
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ bgcolor: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
            <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Avatar sx={{ bgcolor: 'error.main', width: 52, height: 52 }}>
                <HourglassIcon />
              </Avatar>
              <Box>
                <Typography variant="body2" color="text.secondary">Palpites Faltantes</Typography>
                <Typography variant="h4" sx={{ fontWeight: 800, fontFamily: 'Outfit', color: missingPredictions.length > 0 ? 'error.main' : 'text.primary' }}>
                  {missingPredictions.length}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Matches Locking soon */}
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Avatar sx={{ bgcolor: 'info.main', width: 52, height: 52 }}>
                <Badge badgeContent={lockingSoon.length} color="error">
                  <SoccerIcon />
                </Badge>
              </Avatar>
              <Box>
                <Typography variant="body2" color="text.secondary">Bloqueando em 48h</Typography>
                <Typography variant="h5" sx={{ fontWeight: 800, fontFamily: 'Outfit' }}>
                  {lockingSoon.length} jogos
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        {/* Left Side: Quick predictions for upcoming matches */}
        <Grid item xs={12} md={8}>
          <Card sx={{ height: '100%' }}>
            <CardContent sx={{ p: 4 }}>
              <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
                <Typography variant="h5" sx={{ fontWeight: 700, fontFamily: 'Outfit' }}>
                  ⚡ Palpites Rápidos (Próximos Jogos)
                </Typography>
                <Button component={RouterLink} to="/predictions" endIcon={<NextIcon />}>
                  Ver Todos
                </Button>
              </Box>
              
              <Divider sx={{ mb: 3 }} />

              {upcomingMatches.length === 0 ? (
                <Alert severity="success" sx={{ borderRadius: 2 }}>
                  Tudo em dia! Você já deu palpite para todos os próximos jogos.
                </Alert>
              ) : (
                <Stack spacing={3}>
                  {upcomingMatches.map((match) => (
                    <Box 
                      key={match.id}
                      sx={{ 
                        p: 2.5, 
                        borderRadius: 3, 
                        border: '1px solid',
                        borderColor: 'divider',
                        bgcolor: 'background.default',
                        display: 'flex',
                        flexDirection: { xs: 'column', sm: 'row' },
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 2
                      }}
                    >
                      {/* Match Time & Stage */}
                      <Box sx={{ width: { xs: '100%', sm: '20%' }, textAlign: { xs: 'center', sm: 'left' } }}>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontWeight: 600 }}>
                          {match.round}
                        </Typography>
                        <Typography variant="body2" sx={{ fontWeight: 'bold', color: 'primary.main', fontSize: '0.85rem' }}>
                          {formatTime(match.kickoff_time)}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                          📍 {match.ground}
                        </Typography>
                      </Box>

                      {/* Score Input Row */}
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: { xs: 1, sm: 2 }, flexGrow: 1, width: '100%' }}>
                        {/* Team A */}
                        <Typography variant="body1" sx={{ fontWeight: 700, minWidth: { xs: 65, sm: 120 }, textAlign: 'right', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 1 }}>
                          {getFlagUrl(match.team1?.flag_icon, match.team1) ? (
                            <img src={getFlagUrl(match.team1.flag_icon, match.team1)} alt="" style={{ width: 20, height: 14, borderRadius: 1.5, objectFit: 'cover' }} />
                          ) : (
                            <span>{match.team1?.flag_icon}</span>
                          )}
                          <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>
                            {match.team1_name}
                          </Box>
                          <Box component="span" sx={{ display: { xs: 'inline', sm: 'none' } }}>
                            {match.team1?.fifa_code || match.team1_name}
                          </Box>
                        </Typography>
                        
                        {/* Input 1 */}
                        <TextField
                          size="small"
                          sx={{ width: 50 }}
                          inputProps={{ min: 0, style: { textAlign: 'center', fontWeight: 'bold', fontSize: '1.2rem' } }}
                          value={predGoals[match.id]?.goals_team1 ?? ''}
                          onChange={(e) => handleInputChange(match.id, 'goals_team1', e.target.value)}
                        />

                        <Typography variant="body2" sx={{ fontWeight: 'bold', color: 'text.secondary' }}>x</Typography>

                        {/* Input 2 */}
                        <TextField
                          size="small"
                          sx={{ width: 50 }}
                          inputProps={{ min: 0, style: { textAlign: 'center', fontWeight: 'bold', fontSize: '1.2rem' } }}
                          value={predGoals[match.id]?.goals_team2 ?? ''}
                          onChange={(e) => handleInputChange(match.id, 'goals_team2', e.target.value)}
                        />

                        {/* Team B */}
                        <Typography variant="body1" sx={{ fontWeight: 700, minWidth: { xs: 65, sm: 120 }, textAlign: 'left', display: 'flex', alignItems: 'center', justifyContent: 'flex-start', gap: 1 }}>
                          <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>
                            {match.team2_name}
                          </Box>
                          <Box component="span" sx={{ display: { xs: 'inline', sm: 'none' } }}>
                            {match.team2?.fifa_code || match.team2_name}
                          </Box>
                          {getFlagUrl(match.team2?.flag_icon, match.team2) ? (
                            <img src={getFlagUrl(match.team2.flag_icon, match.team2)} alt="" style={{ width: 20, height: 14, borderRadius: 1.5, objectFit: 'cover' }} />
                          ) : (
                            <span>{match.team2?.flag_icon}</span>
                          )}
                        </Typography>
                      </Box>

                      {/* Save Button */}
                      <Box sx={{ width: { xs: '100%', sm: 'auto' }, display: 'flex', justifyContent: 'center' }}>
                        <Button
                          variant={savedPreds[match.id] ? "contained" : "outlined"}
                          color={savedPreds[match.id] ? "success" : "primary"}
                          onClick={() => handleQuickPredictSave(match.id)}
                          startIcon={savedPreds[match.id] ? <SuccessIcon /> : null}
                        >
                          {savedPreds[match.id] ? 'Salvo!' : 'Salvar'}
                        </Button>
                      </Box>
                    </Box>
                  ))}
                </Stack>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Right Side: Invites and My Groups */}
        <Grid item xs={12} md={4}>
          <Stack spacing={3} sx={{ height: '100%' }}>
            {/* Pending Group Invites */}
            {pendingInvites.length > 0 && (
              <Card sx={{ borderColor: 'secondary.main', borderWidth: '1px' }}>
                <CardContent sx={{ p: 3 }}>
                  <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2, display: 'flex', alignItems: 'center', gap: 1, color: 'secondary.main' }}>
                    <GroupInviteIcon /> Convites Pendentes
                  </Typography>
                  <List disablePadding>
                    {pendingInvites.map((invite) => (
                      <Box key={invite.id} sx={{ mb: 2, p: 2, borderRadius: 2, bgcolor: 'background.default', border: '1px dashed #374151' }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          Grupo: {invite.group.name}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
                          Enviado por: {invite.invited_by.display_name}
                        </Typography>
                        <Stack direction="row" spacing={1}>
                          <Button 
                            variant="contained" 
                            color="primary" 
                            size="small"
                            onClick={() => handleInviteResponse(invite.id, true)}
                          >
                            Aceitar
                          </Button>
                          <Button 
                            variant="outlined" 
                            color="error" 
                            size="small"
                            onClick={() => handleInviteResponse(invite.id, false)}
                          >
                            Recusar
                          </Button>
                        </Stack>
                      </Box>
                    ))}
                  </List>
                </CardContent>
              </Card>
            )}

            {/* My Groups Standings */}
            <Card sx={{ flexGrow: 1 }}>
              <CardContent sx={{ p: 3 }}>
                <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                  <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit' }}>
                    🏆 Meus Grupos
                  </Typography>
                  <Button component={RouterLink} to="/groups" size="small">
                    Ver Todos
                  </Button>
                </Box>
                
                <Divider sx={{ mb: 2 }} />

                {stats?.groups?.length === 0 ? (
                  <Box sx={{ py: 3, textStyle: 'center' }}>
                    <Typography variant="body2" color="text.secondary" align="center" sx={{ mb: 2 }}>
                      Você não está participando de nenhum grupo de apostas.
                    </Typography>
                    <Button variant="outlined" component={RouterLink} to="/groups" fullWidth size="small">
                      Criar ou Entrar em um Grupo
                    </Button>
                  </Box>
                ) : (
                  <List disablePadding>
                    {stats?.groups?.map((g) => (
                      <ListItem 
                        key={g.group_id} 
                        disablePadding
                        sx={{ 
                          mb: 1.5,
                          p: 1.5, 
                          borderRadius: 2, 
                          bgcolor: 'background.default', 
                          border: '1px solid #1f2937',
                          cursor: 'pointer',
                          '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.02)' }
                        }}
                        onClick={() => navigate(`/groups/${g.group_id}`)}
                      >
                        <ListItemText 
                          primary={g.group_name} 
                          primaryTypographyProps={{ fontWeight: 600, fontSize: '0.95rem' }}
                          secondary={`Classificação: ${g.position}º lugar`}
                          secondaryTypographyProps={{ color: 'primary.main', fontWeight: 600, fontSize: '0.8rem' }}
                        />
                        <ListItemSecondaryAction sx={{ right: 16 }}>
                          <Typography variant="subtitle1" sx={{ fontWeight: 800, fontFamily: 'Outfit' }}>
                            {g.total_points} pts
                          </Typography>
                        </ListItemSecondaryAction>
                      </ListItem>
                    ))}
                  </List>
                )}
              </CardContent>
            </Card>
          </Stack>
        </Grid>
      </Grid>
    </Box>
  )
}
