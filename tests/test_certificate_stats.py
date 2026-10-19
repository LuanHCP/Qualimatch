from qualimatch.certificate_stats import summarize_phase


def test_summary_uses_printed_statistical_values():
    samples=[
        {'voids_pct':4.3,'ratio_ab_pct':122.5,'thickness_exec_cm':4.9,'thickness_project_cm':4.0},
        {'voids_pct':5.2,'ratio_ab_pct':115.0,'thickness_exec_cm':4.6,'thickness_project_cm':4.0},
        {'voids_pct':3.6,'ratio_ab_pct':115.0,'thickness_exec_cm':4.6,'thickness_project_cm':4.0},
        {'voids_pct':4.0,'ratio_ab_pct':125.0,'thickness_exec_cm':5.0,'thickness_project_cm':4.0},
        {'voids_pct':9.1,'ratio_ab_pct':100.0,'thickness_exec_cm':4.0,'thickness_project_cm':4.0},
    ]
    printed={'k':1.55,'ratio_mean_pct':116.0,'ratio_std_pct':10.0,'ratio_xmin_pct':100.5,'ratio_xmax_pct':131.5,'vv_mean_pct':5.2,'vv_std_pct':2.2,'vv_xmin_pct':1.8,'vv_xmax_pct':8.7}
    s=summarize_phase(samples,printed)
    assert s['vv_mean_pct']==5.2
    assert s['ratio_mean_pct']==116.0
    assert s['thickness_mean_cm']==4.62
    assert s['status_vv']=='REPROVADO'
    assert s['status_thickness']=='APROVADO'
