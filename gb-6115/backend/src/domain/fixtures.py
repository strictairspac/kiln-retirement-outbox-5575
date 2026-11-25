REQUESTS = [
    {"asset": "OV-203", "certificate": "RET-1124-01", "failed_stage": "after_receipt"},
    {"asset": "OV-217", "certificate": "RET-1124-02", "failed_stage": "before_enqueue"},
    {"asset": "OV-225", "certificate": "RET-1124-03", "failed_stage": "none"},
]

FIXTURES = [
    {
        "code": "OV-1124-CLOSE",
        "title": "封板退役批次",
        "description": "包含一台收据写入后断联的烘箱，一台退役事务撤销的烘箱及一台常规退役。",
        "payload": {"observe_until": 40, "requests": REQUESTS},
    },
    {
        "code": "OV-1124-SHORT",
        "title": "短值守窗口",
        "description": "值守观察在第一张证书租约到期前结束，保留待确认事件。",
        "payload": {"observe_until": 3, "requests": REQUESTS},
    },
    {
        "code": "OV-1124-FORMAL",
        "title": "正式封板退役批次",
        "description": "设备组正式登记，整批占用炉号与证书号，交卷后编号继续占用。",
        "payload": {
            "origin": "设备组",
            "requests": [
                {"asset": "OV-251", "certificate": "RET-1124-F1", "failed_stage": "none"},
                {"asset": "OV-252", "certificate": "RET-1124-F2", "failed_stage": "none"},
            ],
        },
    },
]
