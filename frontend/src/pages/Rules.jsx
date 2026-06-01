import React, { useState, useEffect } from 'react'
import {
  Box, Card, CardContent, Typography, Grid, Divider, List, ListItem, ListItemText,
  ListItemIcon, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Stack, CircularProgress
} from '@mui/material'
import {
  HelpOutline as HelpIcon,
  AccessTime as TimeIcon,
  EmojiEvents as PointsIcon,
  TrendingUp as MultIcon,
  CallSplit as TieIcon,
  SportsSoccer as DrawIcon,
  LocalAtm as CashIcon
} from '@mui/icons-material'
import axios from 'axios'

export default function Rules() {
  const [summary, setSummary] = useState(null)
  const [loadingSummary, setLoadingSummary] = useState(true)
  const [predictionLockHours, setPredictionLockHours] = useState(3)
  const [multipliers, setMultipliers] = useState([
    { stage: 'Group Stage', multiplier: 1.0 },
    { stage: 'Round of 32', multiplier: 2.0 },
    { stage: 'Round of 16', multiplier: 3.0 },
    { stage: 'Quarter-finals', multiplier: 4.0 },
    { stage: 'Semi-finals', multiplier: 5.0 },
    { stage: 'Final', multiplier: 6.0 }
  ])

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [summaryRes, settingsRes] = await Promise.all([
          axios.get('/api/payments/summary'),
          axios.get('/api/predictions/settings').catch(() => ({ data: { prediction_lock_hours: 3 } }))
        ])
        setSummary(summaryRes.data)
        setPredictionLockHours(settingsRes.data.prediction_lock_hours ?? 3)
        if (Array.isArray(settingsRes.data.multipliers) && settingsRes.data.multipliers.length > 0) {
          setMultipliers(settingsRes.data.multipliers)
        }
      } catch (err) {
        console.error("Erro ao carregar dados do rateio:", err)
      } finally {
        setLoadingSummary(false)
      }
    }
    fetchData()
  }, [])

  const formatLockHours = (hours) => {
    return Number(hours) === 1 ? '1 hora' : `${hours} horas`
  }

  const getStageLabel = (stage) => {
    const labels = {
      'Group Stage': 'Fase de Grupos',
      'Round of 32': 'Fase de 32 (Dezesseis-avos)',
      'Round of 16': 'Oitavas de Final',
      'Quarter-finals': 'Quartas de Final',
      'Semi-finals': 'Semifinais',
      'Final': 'Disputa de Terceiro Lugar & Final'
    }
    return labels[stage] || stage
  }

  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 3 }}>
        📖 Regras e Funcionamento do Bolão
      </Typography>

      <Grid container spacing={3}>
        {/* Left column: Timing and Scoring */}
        <Grid item xs={12} md={7}>
          <Stack spacing={3}>
            {/* Limit Time Card */}
            <Card sx={{ borderLeft: '5px solid #ef4444' }}>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <TimeIcon color="error" /> Limitação de Horário para Palpites
                </Typography>
                <Divider sx={{ mb: 2 }} />
                <Typography variant="body2" sx={{ lineHeight: 1.7 }} color="text.secondary">
                  O bloqueio para registro ou edição de palpites de qualquer partida ocorre rigorosamente{' '}
                  <strong style={{ color: '#fff' }}>{formatLockHours(predictionLockHours)} antes do horário de início oficial (kickoff)</strong> do jogo.
                </Typography>
                <Typography variant="body2" sx={{ mt: 1.5, lineHeight: 1.7 }} color="text.secondary">
                  Após o bloqueio, os palpites de todos os participantes tornam-se públicos, garantindo total transparência ao bolão.
                </Typography>
              </CardContent>
            </Card>

            {/* Score points rules Card */}
            <Card>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <PointsIcon color="primary" /> Distribuição de Pontos (Placar Base)
                </Typography>
                <Divider sx={{ mb: 2 }} />
                <Typography variant="body2" sx={{ mb: 2 }} color="text.secondary">
                  A pontuação obtida por cada palpite é baseada no nível de acerto do resultado final:
                </Typography>

                <TableContainer component={Paper} sx={{ bgcolor: 'rgba(255,255,255,0.01)', border: '1px solid #1f2937' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold' }}>Tipo de Acerto</TableCell>
                        <TableCell align="center" sx={{ fontWeight: 'bold' }}>Pontos</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>Exemplo (Palpite x Resultado)</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 600 }}>Placar Exato</TableCell>
                        <TableCell align="center" sx={{ fontWeight: 700, color: 'primary.light' }}>10</TableCell>
                        <TableCell color="text.secondary">Palpite 2x1 → Resultado 2x1</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 600 }}>Resultado e Saldo (não exato)</TableCell>
                        <TableCell align="center" sx={{ fontWeight: 700, color: 'primary.light' }}>6</TableCell>
                        <TableCell color="text.secondary">Palpite 3x1 → Resultado 2x0</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 600 }}>Resultado e Gols de 1 Time</TableCell>
                        <TableCell align="center" sx={{ fontWeight: 700, color: 'primary.light' }}>4</TableCell>
                        <TableCell color="text.secondary">Palpite 2x0 → Resultado 2x1</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 600 }}>Apenas Vencedor / Empate</TableCell>
                        <TableCell align="center" sx={{ fontWeight: 700, color: 'primary.light' }}>3</TableCell>
                        <TableCell color="text.secondary">Palpite 3x0 → Resultado 2x1</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 600 }}>Resultado Incorreto</TableCell>
                        <TableCell align="center" sx={{ fontWeight: 700, color: 'error.main' }}>0</TableCell>
                        <TableCell color="text.secondary">Palpite 1x2 → Resultado 1x1</TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>

            {/* Knockout Match / Draw considerations Card */}
            <Card sx={{ borderLeft: '5px solid #10b981' }}>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <DrawIcon color="success" /> Empates nas Fases Eliminatórias (Mata-mata)
                </Typography>
                <Divider sx={{ mb: 2 }} />
                <Typography variant="body2" sx={{ lineHeight: 1.7 }} color="text.secondary">
                  Nas fases de mata-mata, os palpites de placar também são baseados <strong style={{ color: '#fff' }}>apenas no tempo regulamentar</strong> (90 minutos + acréscimos).
                </Typography>
                <Typography variant="body2" sx={{ mt: 1.5, lineHeight: 1.7 }} color="text.secondary">
                  ⚠️ **Importante**: Se você palpitar um empate (ex: 1x1) e a partida terminar empatada no tempo normal, seu palpite será avaliado com base nesse resultado. Gols marcados durante a prorrogação ou na disputa de pênaltis oficial **não** contam para a pontuação do placar do bolão. Não é necessário prever qual time avança na chave.
                </Typography>
              </CardContent>
            </Card>
          </Stack>
        </Grid>

        {/* Right column: Multipliers and Tie-breakers */}
        <Grid item xs={12} md={5}>
          <Stack spacing={3}>
            {/* Rewards and Entry Fee Card */}
            <Card sx={{ borderLeft: '5px solid #eab308' }}>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <CashIcon color="warning" /> Taxa e Rateio da Premiação
                </Typography>
                <Divider sx={{ mb: 2 }} />
                {loadingSummary ? (
                  <Box display="flex" justifyContent="center" py={2}>
                    <CircularProgress size={24} />
                  </Box>
                ) : !summary ? (
                  <Typography variant="body2" color="text.secondary">
                    Informações de premiação indisponíveis.
                  </Typography>
                ) : (
                  <Stack spacing={2}>
                    <Box display="flex" justifyContent="space-between" alignItems="center">
                      <Typography variant="body2" color="text.secondary">Valor da Inscrição:</Typography>
                      <Typography variant="subtitle1" sx={{ fontWeight: 700, color: 'warning.light' }}>
                        R$ {summary.entry_fee.toFixed(2)}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" alignItems="center">
                      <Typography variant="body2" color="text.secondary">Pagamentos Aprovados:</Typography>
                      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                        {summary.approved_payments_count}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" alignItems="center">
                      <Typography variant="body2" color="text.secondary">Total Acumulado:</Typography>
                      <Typography variant="subtitle1" sx={{ fontWeight: 700, color: 'success.main' }}>
                        R$ {summary.total_collected.toFixed(2)}
                      </Typography>
                    </Box>

                    <Divider sx={{ my: 1 }} />
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                      Divisão da Premiação do Bolão:
                    </Typography>

                    <Stack spacing={1}>
                      <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ p: 1, bgcolor: 'rgba(234, 179, 8, 0.05)', borderRadius: 2, borderLeft: '3px solid #eab308' }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>🥇 1º Colocado (50%)</Typography>
                        <Typography variant="body2" sx={{ fontWeight: 700, color: '#eab308' }}>
                          R$ {summary.prizes.first_place.toFixed(2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ p: 1, bgcolor: 'rgba(156, 163, 175, 0.05)', borderRadius: 2, borderLeft: '3px solid #9ca3af' }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>🥈 2º Colocado (30%)</Typography>
                        <Typography variant="body2" sx={{ fontWeight: 700, color: '#9ca3af' }}>
                          R$ {summary.prizes.second_place.toFixed(2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ p: 1, bgcolor: 'rgba(205, 127, 50, 0.05)', borderRadius: 2, borderLeft: '3px solid #cd7f32' }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>🥉 3º Colocado (20%)</Typography>
                        <Typography variant="body2" sx={{ fontWeight: 700, color: '#cd7f32' }}>
                          R$ {summary.prizes.third_place.toFixed(2)}
                        </Typography>
                      </Box>
                    </Stack>
                  </Stack>
                )}
              </CardContent>
            </Card>

            {/* Multipliers Card */}
            <Card>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <MultIcon color="secondary" /> Pesos e Multiplicadores das Fases
                </Typography>
                <Divider sx={{ mb: 2 }} />
                <Typography variant="body2" sx={{ mb: 2 }} color="text.secondary">
                  A pontuação base do seu acerto é multiplicada dependendo da importância da fase da Copa do Mundo:
                </Typography>

                <List disablePadding>
                  {multipliers.map((item, idx) => (
                    <React.Fragment key={item.stage}>
                      <ListItem sx={{ py: 0.75, px: 0 }}>
                        <ListItemText
                          primary={getStageLabel(item.stage)}
                          secondary={`Multiplicador ${Number(item.multiplier).toFixed(1)}x`}
                          primaryTypographyProps={{ fontWeight: 600 }}
                          secondaryTypographyProps={{ color: 'secondary.main', fontWeight: 'bold' }}
                        />
                      </ListItem>
                      {idx < multipliers.length - 1 && <Divider />}
                    </React.Fragment>
                  ))}
                </List>
              </CardContent>
            </Card>

            {/* Tie-breakers Card */}
            <Card>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: 'Outfit', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <TieIcon color="info" /> Critérios de Desempate
                </Typography>
                <Divider sx={{ mb: 2 }} />
                <Typography variant="body2" sx={{ mb: 2 }} color="text.secondary">
                  Em caso de pontuações iguais na classificação, a posição na tabela é decidida seguindo as regras na ordem abaixo:
                </Typography>

                <List disablePadding>
                  {[
                    '1. Maior pontuação total obtida no sistema',
                    '2. Maior número de acertos de Placar Exato (10 pontos)',
                    '3. Maior número de acertos de Resultado Correto (3, 4 ou 6 pontos)',
                    '4. Maior pontuação obtida na fase de mata-mata',
                    '5. Menor quantidade de palpites faltantes em partidas já bloqueadas',
                    '6. Data de cadastro mais antiga no sistema',
                    '7. Ordem alfabética do nome de exibição'
                  ].map((rule, idx) => (
                    <ListItem key={idx} sx={{ py: 0.5, px: 0 }}>
                      <ListItemText primary={rule} primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }} />
                    </ListItem>
                  ))}
                </List>
              </CardContent>
            </Card>
          </Stack>
        </Grid>
      </Grid>
    </Box>
  )
}
