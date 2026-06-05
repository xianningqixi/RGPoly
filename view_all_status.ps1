$workdir = "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket"
Set-Location $workdir

Write-Host "=============================="
Write-Host " Polymarket Bot Status Summary"
Write-Host "=============================="
Write-Host ""

Write-Host "=== Running Python processes ==="
$processes = Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -like "python*" -and (
    $_.CommandLine -like "*btc_signal_bot.py*" -or
    $_.CommandLine -like "*ai_signal_simulator.py*" -or
    $_.CommandLine -like "*polymarket_auto_arb.py*" -or
      $_.CommandLine -like "*watch_creamcream_activity.py*" -or
      $_.CommandLine -like "*creamcream_copy_sim.py*" -or
      $_.CommandLine -like "*smart_wallet_copy_sim.py*" -or
      $_.CommandLine -like "*smart_direction_retest_sim.py*" -or
      $_.CommandLine -like "*btc_directional_wallet_copy_sim.py*" -or
      $_.CommandLine -like "*btc_candidate_discovery_scheduler.py*" -or
      $_.CommandLine -like "*weather_wallet_copy_sim.py*" -or
      $_.CommandLine -like "*weather_high_prob_wallet_copy_sim.py*" -or
      $_.CommandLine -like "*btc_no_dominant_candidate_copy_sim.py*" -or
      $_.CommandLine -like "*eth_high_quality_directional_copy_sim.py*" -or
      $_.CommandLine -like "*oracle_source_monitor.py*" -or
      $_.CommandLine -like "*bond_style_market_scanner.py*" -or
      $_.CommandLine -like "*dashboard_auto_refresh.py*"
    )
  } |
  Select-Object ProcessId, CommandLine
if ($processes) {
  $processes | Format-Table -AutoSize | Out-String | Write-Host
} else {
  Write-Host "No bot Python processes are running."
}

Write-Host ""
Write-Host "=== AI signal simulator ==="
if (Test-Path .\ai_signal_console.log) {
  Get-Content .\ai_signal_console.log -Encoding UTF8 -Tail 8
} else {
  Write-Host "No AI signal simulator log yet."
}
if (Test-Path .\ai_signal_decisions.csv) {
  Write-Host "Recent AI decisions:"
  Get-Content .\ai_signal_decisions.csv -Encoding UTF8 -Tail 5
} else {
  Write-Host "No AI decisions yet."
}
if (Test-Path .\ai_signal_trades.csv) {
  Write-Host "Recent AI simulated trades:"
  Get-Content .\ai_signal_trades.csv -Encoding UTF8 -Tail 5
} else {
  Write-Host "No AI simulated trades yet."
}

Write-Host ""
Write-Host "=== Basket arbitrage scan ==="
if (Test-Path .\dry_run_console.log) {
  Get-Content .\dry_run_console.log -Tail 6
} else {
  Write-Host "No basket scan log yet."
}
if (Test-Path .\dry_run_arb_log.csv) {
  Write-Host "Recent basket simulated trades:"
  Get-Content .\dry_run_arb_log.csv -Tail 5
} else {
  Write-Host "No basket arbitrage simulated trades yet."
}

Write-Host ""
Write-Host "=== BTC signal scan ==="
if (Test-Path .\btc_signal_console.log) {
  Get-Content .\btc_signal_console.log -Tail 8
} else {
  Write-Host "No BTC signal log yet."
}
if (Test-Path .\btc_signal_trades.csv) {
  Write-Host "Recent BTC simulated trades:"
  Get-Content .\btc_signal_trades.csv -Tail 8
} else {
  Write-Host "No BTC simulated trades yet."
}

Write-Host ""
Write-Host "=== CreamCream watcher ==="
if (Test-Path .\creamcream_console.log) {
  Get-Content .\creamcream_console.log -Tail 8
} else {
  Write-Host "No CreamCream log yet."
}
if (Test-Path .\creamcream_activity.csv) {
  Write-Host "Recent CreamCream activity:"
  Get-Content .\creamcream_activity.csv -Tail 5
} else {
  Write-Host "No CreamCream activity records yet."
}

Write-Host ""
Write-Host "=== Weather wallet copy scan ==="
if (Test-Path .\weather_wallet_copy_console.log) {
  Get-Content .\weather_wallet_copy_console.log -Encoding UTF8 -Tail 8
} else {
  Write-Host "No weather wallet copy log yet."
}
if (Test-Path .\weather_wallet_copy_sim.csv) {
  Write-Host "Recent weather wallet simulated trades:"
  Get-Content .\weather_wallet_copy_sim.csv -Encoding UTF8 -Tail 5
} else {
  Write-Host "No weather wallet simulated trades yet."
}

Write-Host ""
Write-Host "=== BTC directional wallet copy scan ==="
if (Test-Path .\btc_directional_copy_console.log) {
  Get-Content .\btc_directional_copy_console.log -Encoding UTF8 -Tail 8
} else {
  Write-Host "No BTC directional copy log yet."
}
if (Test-Path .\btc_directional_wallet_copy_sim.csv) {
  Write-Host "Recent BTC directional simulated trades:"
  Get-Content .\btc_directional_wallet_copy_sim.csv -Encoding UTF8 -Tail 5
} else {
  Write-Host "No BTC directional simulated trades yet."
}

Write-Host ""
Write-Host "=== BTC directional candidate wallet copy scan ==="
if (Test-Path .\btc_directional_candidate_copy_console.log) {
  Get-Content .\btc_directional_candidate_copy_console.log -Encoding UTF8 -Tail 8
} else {
  Write-Host "No BTC directional candidate copy log yet."
}
if (Test-Path .\btc_directional_candidate_copy_sim.csv) {
  Write-Host "Recent BTC directional candidate simulated trades:"
  Get-Content .\btc_directional_candidate_copy_sim.csv -Encoding UTF8 -Tail 5
} else {
  Write-Host "No BTC directional candidate simulated trades yet."
}

Write-Host ""
Write-Host "=== Three added quality-copy directions ==="
foreach ($item in @(
  @{Name="Weather high-prob"; Console="weather_high_prob_wallet_copy_console.log"; Trades="weather_high_prob_wallet_copy_sim.csv"},
  @{Name="BTC No-dominant"; Console="btc_no_dominant_candidate_copy_console.log"; Trades="btc_no_dominant_candidate_copy_sim.csv"},
  @{Name="ETH high-quality"; Console="eth_high_quality_directional_copy_console.log"; Trades="eth_high_quality_directional_copy_sim.csv"}
)) {
  Write-Host "--- $($item.Name) ---"
  if (Test-Path $item.Console) {
    Get-Content $item.Console -Encoding UTF8 -Tail 5
  } else {
    Write-Host "No console log yet."
  }
  if (Test-Path $item.Trades) {
    Get-Content $item.Trades -Encoding UTF8 -Tail 3
  } else {
    Write-Host "No simulated trades yet."
  }
}

Write-Host ""
Write-Host "=== BTC candidate discovery scheduler ==="
if (Test-Path .\btc_candidate_discovery_scheduler_status.txt) {
  Get-Content .\btc_candidate_discovery_scheduler_status.txt -Encoding UTF8 -Tail 3
} else {
  Write-Host "No BTC candidate discovery scheduler status yet."
}
if (Test-Path .\btc_candidate_discovery_scheduler.log) {
  Get-Content .\btc_candidate_discovery_scheduler.log -Encoding UTF8 -Tail 12
} else {
  Write-Host "No BTC candidate discovery scheduler log yet."
}

Write-Host ""
Write-Host "=== Oracle source monitor ==="
if (Test-Path .\oracle_source_console.log) {
  Get-Content .\oracle_source_console.log -Encoding UTF8 -Tail 5
} else {
  Write-Host "No oracle source monitor log yet."
}
if (Test-Path .\oracle_source_map.csv) {
  Import-Csv .\oracle_source_map.csv | Select-Object -Last 5 slug,category,resolution_source,source_url | Format-Table -AutoSize
} else {
  Write-Host "No oracle source map yet."
}

Write-Host ""
Write-Host "=== Smart direction retest ==="
if (Test-Path .\smart_direction_retest_console.log) {
  Get-Content .\smart_direction_retest_console.log -Encoding UTF8 -Tail 8
} else {
  Write-Host "No smart direction retest log yet."
}
if (Test-Path .\smart_direction_retest_sim.csv) {
  Write-Host "Recent smart direction retest simulated trades:"
  Get-Content .\smart_direction_retest_sim.csv -Encoding UTF8 -Tail 5
} else {
  Write-Host "No smart direction retest simulated trades yet."
}

Write-Host ""
Write-Host "=== Bond-style market scanner ==="
if (Test-Path .\bond_style_console.log) {
  Get-Content .\bond_style_console.log -Encoding UTF8 -Tail 8
} else {
  Write-Host "No bond-style scanner log yet."
}
if (Test-Path .\bond_style_candidates.csv) {
  Import-Csv .\bond_style_candidates.csv |
    Select-Object -Last 5 ts,scan_id,category,outcome,sim_fill_price,spread,hours_to_end,title |
    Format-Table -AutoSize -Wrap
} else {
  Write-Host "No bond-style candidates yet."
}

Write-Host ""
Write-Host "=== Latest alerts ==="
foreach ($file in @("latest_arb_alert.txt", "latest_btc_signal.txt", "latest_creamcream_alert.txt", "latest_creamcream_copy_alert.txt", "latest_smart_wallet_copy_alert.txt", "latest_smart_direction_retest_alert.txt", "latest_weather_wallet_copy_alert.txt", "latest_weather_high_prob_wallet_copy_alert.txt", "latest_btc_no_dominant_candidate_copy_alert.txt", "latest_eth_high_quality_directional_copy_alert.txt", "latest_bond_style_alert.txt")) {
  Write-Host "--- $file ---"
  if (Test-Path $file) {
    $item = Get-Item $file
    $age = (Get-Date) - $item.LastWriteTime
    $ageText = "{0:N1}h old" -f $age.TotalHours
    if ($age.TotalHours -gt 2) {
      Write-Host "STALE ALERT: $ageText. Treat this as old context, not a new signal."
    } else {
      Write-Host "Fresh alert: $ageText."
    }
    Get-Content $file
  } else {
    Write-Host "No alert file."
  }
}

Write-Host ""
Write-Host "=== Strategy runtime status ==="
python .\runtime_strategy_status.py
if (Test-Path .\runtime_strategy_status.csv) {
  Import-Csv .\runtime_strategy_status.csv |
    Select-Object strategy,intended_state,runtime_state,pid,status,note |
    Format-Table -AutoSize -Wrap
}

Write-Host ""
Write-Host "=== Data quality / final coverage ==="
python .\audit_backfill_scheduler.py --once --batch-limit 40
python .\data_quality_report.py --once
if (Test-Path .\data_quality_report.csv) {
  Import-Csv .\data_quality_report.csv |
    Select-Object strategy,final_rows,pending_rows,final_coverage_pct,pending_stake_usdc,oldest_pending_age_hours,data_quality,recommended_action |
    Format-Table -AutoSize -Wrap
}
if (Test-Path .\audit_backfill_summary.csv) {
  Write-Host ""
  Write-Host "Recent audit backfill:"
  Import-Csv .\audit_backfill_summary.csv |
    Select-Object -Last 10 ts,strategy,before_pending,after_pending,new_final,status |
    Format-Table -AutoSize -Wrap
}

Write-Host ""
Write-Host "=== Current config performance ==="
python .\current_config_report.py --once
if (Test-Path .\current_config_report.csv) {
  Import-Csv .\current_config_report.csv |
    Select-Object strategy,intended_state,total_since_cutoff,final_since_cutoff,pending_since_cutoff,pnl,roi,status |
    Format-Table -AutoSize -Wrap
}

Write-Host ""
Write-Host "=== Signal rejects / missed opportunity funnel ==="
python .\signal_reject_report.py --once
python .\active_signal_funnel.py --once
if (Test-Path .\signal_reject_report.csv) {
  Import-Csv .\signal_reject_report.csv |
    Select-Object strategy,reason,count,avg_signal_age_sec,avg_slippage_bps,avg_source_to_ask_gap |
    Format-Table -AutoSize -Wrap
}
if (Test-Path .\active_signal_funnel.csv) {
  Write-Host ""
  Write-Host "Recent source activity funnel:"
  Import-Csv .\active_signal_funnel.csv |
    Select-Object strategy,reason,count,avg_signal_age_sec |
    Format-Table -AutoSize -Wrap
}

Write-Host ""
Write-Host "=== BTC directional candidate rotation ==="
python .\btc_directional_candidate_rotation_report.py --once
if (Test-Path .\btc_directional_candidate_rotation_report.csv) {
  Import-Csv .\btc_directional_candidate_rotation_report.csv |
    Where-Object { $_.action -in @("PROMOTE_CANDIDATE", "KEEP_OBSERVING", "ADD_TO_OBSERVATION", "DOWNWEIGHT_OBSERVATION") } |
    Select-Object -First 12 action,alias,candidate_rank,discovery_recommendation,sim_final,sim_pending,sim_final_roi,positive_2m_rate,positive_10m_rate,reason |
    Format-Table -AutoSize -Wrap
}

Write-Host ""
Write-Host "=== Market direction score ==="
python .\market_direction_report.py --once
if (Test-Path .\market_direction_report.csv) {
  Import-Csv .\market_direction_report.csv |
    Where-Object { $_.action -in @("PRIMARY_CANDIDATE", "OBSERVE_TO_PROMOTE", "RETEST_TINY", "OBSERVE_PENDING", "DOWNWEIGHT", "STOP", "STOP_OR_TINY_OBSERVE", "BLOCK") } |
    Select-Object -First 15 action,direction,strategy,final,pending,wins,losses,pnl,roi,reason |
    Format-Table -AutoSize -Wrap
}

Write-Host ""
Write-Host "=== Capital allocation ==="
python .\capital_allocation_report.py --once
if (Test-Path .\capital_allocation_report.csv) {
  Import-Csv .\capital_allocation_report.csv |
    Select-Object tier,strategy,max_new_trade_stake_usdc,max_open_stake_usdc,realized,pending,pnl,roi,action,reason |
    Format-Table -AutoSize -Wrap
}

Write-Host ""
Write-Host "=== Performance summary ==="
python .\summarize_bot_performance.py
