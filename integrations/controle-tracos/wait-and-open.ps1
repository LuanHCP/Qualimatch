# Espera o servidor local (porta 3000) comecar a responder antes de abrir o
# navegador, em vez de abrir depois de um tempo fixo - o site pode demorar
# bem mais que alguns segundos para iniciar na primeira vez, ou quando ha
# dependencias novas para o npm instalar. Espera no maximo 3 minutos.
$deadline = (Get-Date).AddSeconds(180)
$ok = $false
while ((Get-Date) -lt $deadline) {
  try {
    (New-Object System.Net.Sockets.TcpClient('127.0.0.1', 3000)).Close()
    $ok = $true
    break
  } catch {
    Start-Sleep -Seconds 1
  }
}
if ($ok) {
  Start-Process 'http://localhost:3000'
}
