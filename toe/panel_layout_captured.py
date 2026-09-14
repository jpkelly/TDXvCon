#: Full capture of JP's hand-tuned panel (v3)
#: {name: {'geometry': {...}, 'pars': {...},
#:          'expressions': {par: expr}}} — OP refs are paths,
#: 'panel' holds the panel CONTAINER's own settings;
#: 'listerconfig' (queue only) = {DAT name: text}.
CAPTURED_PANEL = {
    "panel": {
        "geometry": {'x': 0, 'y': 0, 'w': 660, 'h': 640},
        "pars": {},
    },
    "status_l": {
        "geometry": {'x': 20, 'y': 40, 'w': 620, 'h': 30},
        "pars": {'Widgetlabel': 'idle — listening on port 7999', 'Labelwidth': 110},
        "expressions": {'Widgetlabel': 'op.vcon.par.Status', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "queue": {
        "geometry": {'x': 20, 'y': 90, 'w': 620, 'h': 200},
        "pars": {'Inputtabledat': '/project1/vcon/queue_display', 'Drophighlight': 'Row', 'Configcomp': '/project1/vcon/panel/listerConfig', 'Callbackdat': '/project1/vcon/panel/listerConfig/callbacks', 'Version': '1.22.4', 'Toxsavebuild': '2025.32702'},
        "expressions": {'Callbackdat': "me.par.Configcomp.eval().op('callbacks') if me.par.Configcomp else ''"},
    },
    "prog_fill": {
        "geometry": {'x': 20, 'y': 330, 'w': 0, 'h': 16},
        "pars": {},
    },
    "prog_track": {
        "geometry": {'x': 20, 'y': 330, 'w': 620, 'h': 16},
        "pars": {},
    },
    "output_l": {
        "geometry": {'x': 20, 'y': 375, 'w': 620, 'h': 30},
        "pars": {'Widgetlabel': '(queue is empty — add files)', 'Labelwordwrap': True, 'Labelhorizontalmode': 'fill', 'Labelwidth': 110},
        "expressions": {'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "start_b": {
        "geometry": {'x': 20, 'y': 420, 'w': 100, 'h': 30},
        "pars": {'Offtoonscript0': "op.vcon.op('panel_callbacks').module.Start()", 'Widgetlabel': '', 'Labelwidth': 1, 'Buttonofflabel': 'START', 'Buttononlabel': 'START'},
        "expressions": {'Buttonofflabel': 'chr(0xF070E)', 'Buttononlabel': 'chr(0xF070E)', 'Buttonofffontcolorr': 'None', 'Buttonofffontcolorg': 'None', 'Buttonofffontcolorb': 'None', 'Buttonofffontcolora': 'None', 'Buttononfontcolorr': 'None', 'Buttononfontcolorg': 'None', 'Buttononfontcolorb': 'None', 'Buttononfontcolora': 'None', 'Buttonbordercolorr': 'None', 'Buttonbordercolorg': 'None', 'Buttonbordercolorb': 'None', 'Buttonbordercolora': 'None', 'Buttonstateexpression': 'None', 'Buttonpanelexec': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "pause_b": {
        "geometry": {'x': 120, 'y': 420, 'w': 100, 'h': 30},
        "pars": {'Offtoonscript0': "op.vcon.op('panel_callbacks').module.PauseResume()", 'Widgetlabel': '', 'Labelwidth': 1, 'Buttonofflabel': 'PAUSE', 'Buttononlabel': 'PAUSE'},
        "expressions": {'Buttonofflabel': 'chr(0xF070E)', 'Buttononlabel': 'chr(0xF070E)', 'Buttonofffontcolorr': 'None', 'Buttonofffontcolorg': 'None', 'Buttonofffontcolorb': 'None', 'Buttonofffontcolora': 'None', 'Buttononfontcolorr': 'None', 'Buttononfontcolorg': 'None', 'Buttononfontcolorb': 'None', 'Buttononfontcolora': 'None', 'Buttonbordercolorr': 'None', 'Buttonbordercolorg': 'None', 'Buttonbordercolorb': 'None', 'Buttonbordercolora': 'None', 'Buttonstateexpression': 'None', 'Buttonpanelexec': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "stop_b": {
        "geometry": {'x': 220, 'y': 420, 'w': 100, 'h': 30},
        "pars": {'Offtoonscript0': "op.vcon.op('panel_callbacks').module.Stop()", 'Widgetlabel': '', 'Labelwidth': 1, 'Buttonofflabel': 'STOP', 'Buttononlabel': 'STOP'},
        "expressions": {'Buttonofflabel': 'chr(0xF070E)', 'Buttononlabel': 'chr(0xF070E)', 'Buttonofffontcolorr': 'None', 'Buttonofffontcolorg': 'None', 'Buttonofffontcolorb': 'None', 'Buttonofffontcolora': 'None', 'Buttononfontcolorr': 'None', 'Buttononfontcolorg': 'None', 'Buttononfontcolorb': 'None', 'Buttononfontcolora': 'None', 'Buttonbordercolorr': 'None', 'Buttonbordercolorg': 'None', 'Buttonbordercolorb': 'None', 'Buttonbordercolora': 'None', 'Buttonstateexpression': 'None', 'Buttonpanelexec': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "add_b": {
        "geometry": {'x': 320, 'y': 420, 'w': 100, 'h': 30},
        "pars": {'Offtoonscript0': "op.vcon.op('panel_callbacks').module.AddFiles()", 'Widgetlabel': '', 'Labelwidth': 1, 'Buttonofflabel': '+ ADD', 'Buttononlabel': '+ ADD'},
        "expressions": {'Buttonofflabel': 'chr(0xF070E)', 'Buttononlabel': 'chr(0xF070E)', 'Buttonofffontcolorr': 'None', 'Buttonofffontcolorg': 'None', 'Buttonofffontcolorb': 'None', 'Buttonofffontcolora': 'None', 'Buttononfontcolorr': 'None', 'Buttononfontcolorg': 'None', 'Buttononfontcolorb': 'None', 'Buttononfontcolora': 'None', 'Buttonbordercolorr': 'None', 'Buttonbordercolorg': 'None', 'Buttonbordercolorb': 'None', 'Buttonbordercolora': 'None', 'Buttonstateexpression': 'None', 'Buttonpanelexec': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "fps_f": {
        "geometry": {'x': 20, 'y': 465, 'w': 73, 'h': 30},
        "pars": {'Value0': 'auto', 'Widgetlabel': 'FPS', 'Labelwidth': 32},
        "expressions": {'Stringfieldoffsetx': 'None', 'Stringfieldoffsety': 'None', 'Stringfieldpanelexec': 'None', 'Stringfieldwidth': 'None', 'Stringfieldhfillweight': 'None', 'Stringfieldheight': 'None', 'Stringfieldvfillweight': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "scaled_t": {
        "geometry": {'x': 92, 'y': 465, 'w': 104, 'h': 30},
        "pars": {'Value0': True, 'Onvaluechangescript0': "op.vcon.op('panel_callbacks').module._update_res_fields()", 'Widgetlabel': 'SCALING', 'Labelwidth': 60, 'Buttonofflabel': 'OFF', 'Buttononlabel': 'ON', 'Buttonwidth': 33},
        "expressions": {'Buttonofffontcolorr': 'None', 'Buttonofffontcolorg': 'None', 'Buttonofffontcolorb': 'None', 'Buttonofffontcolora': 'None', 'Buttononfontcolorr': 'None', 'Buttononfontcolorg': 'None', 'Buttononfontcolorb': 'None', 'Buttononfontcolora': 'None', 'Buttonbordercolorr': 'None', 'Buttonbordercolorg': 'None', 'Buttonbordercolorb': 'None', 'Buttonbordercolora': 'None', 'Buttonstateexpression': 'None', 'Buttonpanelexec': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "scale_dd": {
        "geometry": {'x': 195, 'y': 465, 'w': 145, 'h': 30},
        "pars": {'Value0': 'custom', 'Onvaluechangescript0': "op.vcon.op('panel_callbacks').module._update_res_fields()", 'Widgetlabel': 'SCALE', 'Labelwidth': 60, 'Menunames': '0.5 0.333 0.25 2 3 4 custom', 'Menulabels': "'Half (1/2x)' 'Third (1/3x)' 'Quarter (1/4x)' 'Two times (2x)' 'Three times (3x)' 'Four times (4x)' Custom"},
        "expressions": {'Menuitemverticalpadding': 'None', 'Menuitemhorizontalpadding1': 'None', 'Menupanelexec': 'None', 'Menubuttonfontsize': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "resw_f": {
        "geometry": {'x': 340, 'y': 465, 'w': 85, 'h': 30},
        "pars": {'Value0': '1920', 'Widgetlabel': 'W', 'Labelwidth': 20},
        "expressions": {'Stringfieldoffsetx': 'None', 'Stringfieldoffsety': 'None', 'Stringfieldpanelexec': 'None', 'Stringfieldwidth': 'None', 'Stringfieldhfillweight': 'None', 'Stringfieldheight': 'None', 'Stringfieldvfillweight': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "resh_f": {
        "geometry": {'x': 424, 'y': 465, 'w': 85, 'h': 30},
        "pars": {'Value0': '1080', 'Widgetlabel': 'H', 'Labelwidth': 20},
        "expressions": {'Labelwidth': '2o', 'Stringfieldoffsetx': 'None', 'Stringfieldoffsety': 'None', 'Stringfieldpanelexec': 'None', 'Stringfieldwidth': 'None', 'Stringfieldhfillweight': 'None', 'Stringfieldheight': 'None', 'Stringfieldvfillweight': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "fit_dd": {
        "geometry": {'x': 507, 'y': 465, 'w': 131, 'h': 30},
        "pars": {'Value0': 'fitbest', 'Widgetlabel': 'FIT', 'Labelwidth': 26, 'Menunames': 'fitbest fill fithorz fitvert fitoutside', 'Menulabels': "'Fit Best' Stretch 'Fit Width' 'Fit Height' Cover/Crop"},
        "expressions": {'Menuitemverticalpadding': 'None', 'Menuitemhorizontalpadding1': 'None', 'Menupanelexec': 'None', 'Menubuttonfontsize': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "subtype_dd": {
        "geometry": {'x': 20, 'y': 510, 'w': 230, 'h': 30},
        "pars": {'Value0': '', 'Onvaluechangescript0': "op.vcon.op('panel_callbacks').module.UpdateSubtypes(); op.vcon.op('panel_callbacks').module.OnSelectionChanged()", 'Widgetlabel': 'SUBTYPE', 'Labelwidth': 90, 'Menunames': ''},
        "expressions": {'Menuitemverticalpadding': 'None', 'Menuitemhorizontalpadding1': 'None', 'Menupanelexec': 'None', 'Menubuttonfontsize': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "quality_s": {
        "geometry": {'x': 260, 'y': 510, 'w': 230, 'h': 30},
        "pars": {'Value0': 0.862, 'Onvaluechangescript0': "op.vcon.op('panel_callbacks').module.OnQualityChanged()", 'Widgetlabel': 'QUALITY', 'Labelwidth': 90, 'Sliderlabelnames': "'0.0 Good' '0.285 Very Good' '0.575 Excellent' '0.862 Optimal' '1.0 Best'"},
        "expressions": {'Labelfontsize': "me.LookVal('Labelfontsize')", 'Labeloffsetx': "me.LookVal('Labeloffset', 0)", 'Labeloffsety': "me.LookVal('Labeloffset', 1)", 'Labelwidth': "me.LookVal('Labelwidth')", 'Labelhfillweight': "me.LookVal('Labelhfillweight')", 'Labelheight': "me.LookVal('Labelheight')", 'Labelvfillweight': "me.LookVal('Labelvfillweight')", 'Numericfieldoffsetx': 'None', 'Numericfieldoffsety': 'None', 'Numericfieldpanelexec': 'None', 'Sliderpanelexec': 'None', 'Cacheabletop': "op('./slider0/bg')", 'Cachefiltercolorr': 'None', 'Cachefiltercolorg': 'None', 'Cachefiltercolorb': 'None', 'Cachefiltercolora': 'None', 'Rollovercolorg': "me.LookVal('Rollovercolor', 1)", 'Rollovercolorb': "me.LookVal('Rollovercolor', 2)", 'Rollovercolora': "me.LookVal('Rollovercolor', 3)", 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "codec_dd": {
        "geometry": {'x': 20, 'y': 555, 'w': 230, 'h': 30},
        "pars": {'Value0': 'notchlc', 'Onvaluechangescript0': "op.vcon.op('panel_callbacks').module.UpdateSubtypes(); op.vcon.op('panel_callbacks').module.OnSelectionChanged()", 'Widgetlabel': 'CODEC', 'Labelwidth': 90, 'Menunames': 'notchlc hap cineform prores h264 h265 av1', 'Menulabels': "NotchLC Hap 'GoPro CineForm' 'Apple ProRes' H.264 H.265 AV1"},
        "expressions": {'Menuitemverticalpadding': 'None', 'Menuitemhorizontalpadding1': 'None', 'Menupanelexec': 'None', 'Menubuttonfontsize': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "format_dd": {
        "geometry": {'x': 260, 'y': 555, 'w': 230, 'h': 30},
        "pars": {'Value0': 'rgb', 'Onvaluechangescript0': "op.vcon.op('panel_callbacks').module.OnSelectionChanged()", 'Widgetlabel': 'FORMAT', 'Labelwidth': 90, 'Menunames': 'rgb rgba', 'Menulabels': "'RGB' 'RGB + Alpha'"},
        "expressions": {'Menuitemverticalpadding': 'None', 'Menuitemhorizontalpadding1': 'None', 'Menupanelexec': 'None', 'Menubuttonfontsize': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
    "destination": {
        "geometry": {'x': 20, 'y': 600, 'w': 620, 'h': 30},
        "pars": {'Onvaluechangescript0': "op.vcon.op('panel_callbacks').module.PreviewOutput()", 'Widgetlabel': 'DESTINATION', 'Labelwidth': 110},
        "expressions": {'Stringfieldoffsetx': 'None', 'Stringfieldoffsety': 'None', 'Stringfieldpanelexec': 'None', 'Stringfieldwidth': 'None', 'Stringfieldhfillweight': 'None', 'Stringfieldheight': 'None', 'Stringfieldvfillweight': 'None', 'Buttonlabel': 'chr(0xF0770)', 'Buttonofffontcolorr': 'None', 'Buttonofffontcolorg': 'None', 'Buttonofffontcolorb': 'None', 'Buttonofffontcolora': 'None', 'Buttononfontcolorr': 'None', 'Buttononfontcolorg': 'None', 'Buttononfontcolorb': 'None', 'Buttononfontcolora': 'None', 'Buttonbordercolorr': 'None', 'Buttonbordercolorg': 'None', 'Buttonbordercolorb': 'None', 'Buttonbordercolora': 'None', 'Buttonpanelexec': 'None', 'Buttonfieldmargin': 'None', 'Disablecolorr': 'None', 'Disablecolorg': 'None', 'Disablecolorb': 'None', 'Disablecolora': 'None'},
    },
}
