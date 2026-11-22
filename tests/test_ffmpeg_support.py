"""Shared FFmpeg discovery/validation, without TouchDesigner or real installs."""

import importlib.util
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from td_fakes import ffmpeg_report

ROOT = Path(__file__).resolve().parents[1]


def load_source(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'toe' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def controller():
    return load_source('vcon_controller')


@pytest.fixture
def panel():
    module = load_source('vcon_panel_callbacks')
    module.note = lambda *args: None
    module._set_output_text = lambda *args: None
    module.PreviewOutput = lambda: None
    return module


def executable(tmp_path, name='ffmpeg'):
    path = tmp_path / name
    path.write_bytes(b'fake executable')
    path.chmod(0o755)
    return str(path)


def scan(discovery):
    discovery._scan(discovery._generation)
    return discovery._reply[1]


def settle(discovery, refresh=False):
    report = discovery.status(refresh=refresh)
    for _ in range(3):
        if report['state'] != 'checking':
            return report
        discovery._thread.join(timeout=3)
        report = discovery.status()
    pytest.fail('discovery did not settle')


@pytest.fixture
def isolated_candidates(controller, monkeypatch, tmp_path):
    """No installed packages, conda binary or PATH candidates on this host."""
    import shutil
    monkeypatch.setitem(sys.modules, 'imageio_ffmpeg',
                        SimpleNamespace(__file__=str(tmp_path / 'package' / '__init__.py')))
    monkeypatch.setattr(shutil, 'which', lambda value: None)
    monkeypatch.delenv('IMAGEIO_FFMPEG_EXE', raising=False)
    monkeypatch.setattr(controller, 'sys', SimpleNamespace(platform='darwin',
                                                          prefix=str(tmp_path)))
    return controller


def test_finder_path_still_searches_homebrew_and_macports(isolated_candidates, monkeypatch):
    monkeypatch.setenv('PATH', '/usr/bin:/bin:/usr/sbin:/sbin')
    candidates = list(isolated_candidates._ffmpeg_candidates())
    assert candidates[-3:] == [
        ('Homebrew', '/opt/homebrew/bin/ffmpeg'),
        ('Homebrew', '/usr/local/bin/ffmpeg'),
        ('MacPorts', '/opt/local/bin/ffmpeg'),
    ]


def test_windows_package_manager_locations(isolated_candidates, monkeypatch, tmp_path):
    module = isolated_candidates
    monkeypatch.setattr(module.sys, 'platform', 'win32')
    monkeypatch.setattr(module, 'os', SimpleNamespace(
        name='nt', path=os.path, environ=os.environ))
    for name in ('LOCALAPPDATA', 'ProgramData', 'USERPROFILE'):
        monkeypatch.setenv(name, str(tmp_path / name))
    candidates = dict(module._ffmpeg_candidates())
    for source, variable, suffix in (
            ('WinGet', 'LOCALAPPDATA', 'Microsoft/WinGet/Links/ffmpeg.exe'),
            ('Chocolatey', 'ProgramData', 'chocolatey/bin/ffmpeg.exe'),
            ('Scoop', 'USERPROFILE', 'scoop/shims/ffmpeg.exe')):
        assert candidates[source] == str(tmp_path / variable / suffix)


def test_user_site_and_modern_pipx_are_in_discovery(isolated_candidates, monkeypatch):
    import glob
    patterns = []
    monkeypatch.setattr(glob, 'glob', lambda pattern: patterns.append(pattern) or [])
    list(isolated_candidates._ffmpeg_candidates())
    assert any('/.local/lib/python*/site-packages/' in p for p in patterns)
    assert any('/.local/share/pipx/venvs/' in p for p in patterns)


@pytest.fixture
def probe_output(monkeypatch):
    outputs = {
        '-version': 'ffmpeg version 7.1 Copyright\n',
        '-muxers': 'Muxers:\n E = Muxing supported\n --\n E mov QuickTime\n'
                   ' E matroska,webm Matroska\n E mp4 MP4\n',
        '-encoders': 'Encoders:\n A..... = Audio\n ------\n A....D aac AAC\n'
                     ' A..... libopus Opus\n A..... pcm_s24le PCM\n',
    }
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs['timeout'] == 15
        assert kwargs['stdin'] == subprocess.DEVNULL
        return SimpleNamespace(returncode=0, stdout=outputs[command[-1]], stderr='')

    monkeypatch.setattr(subprocess, 'run', run)
    return outputs, calls


def test_probe_parses_version_muxer_aliases_and_real_encoder_names(controller, probe_output):
    result = controller._ffmpeg_probe('/fake/ffmpeg')
    assert result['version'] == '7.1'
    assert result['muxers'] == {'mov', 'mp4', 'matroska', 'webm'}
    assert result['encoders'] == {'aac', 'libopus', 'pcm_s24le'}
    assert controller._ffmpeg_missing(result, 'opus', '.webm') == []
    assert '=' not in result['muxers'] | result['encoders']
    assert len(probe_output[1]) == 3


@pytest.mark.parametrize('option', ['-version', '-muxers', '-encoders'])
def test_probe_requires_zero_exit_for_every_command(controller, monkeypatch, option):
    def run(command, **kwargs):
        return SimpleNamespace(returncode=1 if command[-1] == option else 0,
                               stdout='ffmpeg version 7.1\n', stderr='blocked')
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(ValueError, match=f'{option} exited 1: blocked'):
        controller._ffmpeg_probe('/fake/ffmpeg')


def test_probe_times_out_with_actionable_reason(controller, monkeypatch):
    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 2)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(controller._ProbeTimeout, match='timed out after 15 seconds'):
        controller._ffmpeg_probe('/fake/ffmpeg')


def test_unrelated_program_cannot_pass_version_check(controller, probe_output):
    probe_output[0]['-version'] = 'other program 7.1\n'
    with pytest.raises(ValueError, match='did not identify'):
        controller._ffmpeg_probe('/fake/ffmpeg')


def test_broken_binary_falls_back_and_results_are_cached(controller, monkeypatch, tmp_path):
    bad, good = executable(tmp_path, 'broken'), executable(tmp_path, 'working')
    monkeypatch.setattr(controller, '_ffmpeg_candidates',
                        lambda: iter([('download', bad), ('Homebrew', good)]))
    calls = []

    def probe(path):
        calls.append(path)
        if path == bad:
            raise OSError('wrong architecture')
        return ffmpeg_report(path)

    monkeypatch.setattr(controller, '_ffmpeg_probe', probe)
    discovery = controller._FFmpegDiscovery()
    for _ in range(2):
        result = scan(discovery)
        assert result['path'] == good
        assert result['source'] == 'Homebrew'
        assert 'wrong architecture' in result['failures'][0]
    assert calls == [bad, good]
    Path(bad).write_bytes(b'replacement binary')
    scan(discovery)
    assert calls == [bad, good, bad]


def test_symlink_candidates_are_deduplicated(controller, monkeypatch, tmp_path):
    path = executable(tmp_path)
    alias = tmp_path / 'alias'
    try:
        alias.symlink_to(path)
    except OSError:
        pytest.skip('symlinks unavailable')
    monkeypatch.setattr(controller, '_ffmpeg_candidates',
                        lambda: iter([('one', path), ('two', str(alias))]))
    calls = []

    def fail(path):
        calls.append(path)
        raise ValueError('unusable')

    monkeypatch.setattr(controller, '_ffmpeg_probe', fail)
    result = scan(controller._FFmpegDiscovery())
    assert result['state'] == 'invalid'
    assert calls == [path]


def test_missing_install_is_discovered_without_restart(controller, monkeypatch, tmp_path):
    path = str(tmp_path / 'ffmpeg')
    monkeypatch.setattr(controller, '_ffmpeg_candidates', lambda: iter([('download', path)]))
    monkeypatch.setattr(controller, '_ffmpeg_probe', ffmpeg_report)
    discovery = controller._FFmpegDiscovery()
    assert settle(discovery)['state'] == 'missing'
    executable(tmp_path)
    assert settle(discovery, refresh=True)['path'] == path


def test_manual_recheck_retries_unchanged_failed_binary(controller, monkeypatch, tmp_path):
    path = executable(tmp_path)
    monkeypatch.setattr(controller, '_ffmpeg_candidates', lambda: iter([('download', path)]))
    calls = []

    def probe(path):
        calls.append(path)
        if len(calls) == 1:
            raise PermissionError('OS security block')
        return ffmpeg_report(path)

    monkeypatch.setattr(controller, '_ffmpeg_probe', probe)
    discovery = controller._FFmpegDiscovery()
    assert settle(discovery)['state'] == 'invalid'
    assert settle(discovery, refresh=True)['state'] == 'ready'
    assert len(calls) == 2


def test_check_is_nonblocking_and_refresh_discards_inflight_result(controller, monkeypatch,
                                                                  tmp_path):
    path = executable(tmp_path)
    monkeypatch.setattr(controller, '_ffmpeg_candidates', lambda: iter([('download', path)]))
    entered, release = threading.Event(), threading.Event()
    calls = []

    def probe(path):
        calls.append(path)
        entered.set()
        assert release.wait(3)
        return ffmpeg_report(path)

    monkeypatch.setattr(controller, '_ffmpeg_probe', probe)
    discovery = controller._FFmpegDiscovery()
    try:
        assert discovery.status()['state'] == 'checking'
        assert entered.wait(3)
        assert discovery.status(refresh=True)['state'] == 'checking'
    finally:
        release.set()
    assert settle(discovery)['state'] == 'ready'
    assert len(calls) == 2


@pytest.mark.parametrize(('audio', 'extension', 'sep', 'expected'), [
    ('aac', '.mp4', None, []),
    ('copy', '.mov', None, []),
    ('opus', '.webm', None, ['encoder libopus']),
    ('none', '.mov', 'aiff24', ['encoder pcm_s24be']),
    ('none', '.mov', 'copy', []),
    ('none', '.mov', 'aac', ['muxer ipod']),
])
def test_capabilities_only_restrict_affected_operations(controller, audio, extension, sep,
                                                        expected):
    report = ffmpeg_report('/fake')
    report['encoders'] -= {'libopus', 'pcm_s24be'}
    report['muxers'] -= {'ipod'}
    assert controller._ffmpeg_missing(report, audio, extension, sep) == expected


def test_panel_delegates_selected_audio_to_controller(panel, monkeypatch):
    calls = []
    selected = dict(audio_dd='opus', container_dd='webm', audio_sep_t=True,
                    audio_sep_dd='aiff24')
    monkeypatch.setattr(panel, '_val', selected.get)
    report = {'state': 'invalid', 'error': 'wrong architecture'}
    monkeypatch.setattr(panel, 'ext', lambda: SimpleNamespace(
        FFmpegStatus=lambda **kw: calls.append(kw) or report))
    assert panel._ffmpeg_status(refresh=True) is report
    assert calls == [dict(refresh=True, audio='opus', extension='.webm', audio_sep='aiff24')]


def test_installer_waits_for_validation_and_invalidates_once(panel, monkeypatch):
    calls = []
    reports = iter([{'state': 'checking'}, ffmpeg_report('/new/ffmpeg')])
    monkeypatch.setattr(panel, '_ffmpeg_status',
                        lambda **kw: calls.append(kw) or next(reports))
    panel._install = dict(proc=SimpleNamespace(poll=lambda: 0),
                          log=SimpleNamespace(close=lambda: None))
    panel._install_tick()
    assert panel._install is not None
    panel._install_tick()
    assert panel._install is None
    assert calls == [dict(refresh=True), dict(refresh=False)]


@pytest.mark.parametrize(('state', 'label'), [
    ('missing', 'NOT INSTALLED'), ('invalid', 'UNUSABLE'),
    ('unsupported', 'UNSUPPORTED SELECTION'), ('checking', 'CHECKING'),
    ('ready', 'READY'),
])
def test_setup_dialog_reports_validation_state_and_preserves_install_action(
        panel, monkeypatch, state, label):
    report = {**ffmpeg_report('/fake/ffmpeg'), 'state': state,
              'error': 'wrong architecture' if state == 'invalid' else 'Missing encoder aac'}
    monkeypatch.setattr(panel, '_ffmpeg_status', lambda: report)
    monkeypatch.setattr(panel, '_python_for_pip', lambda: None)
    monkeypatch.setattr(panel, '_cli_version', lambda: None)
    monkeypatch.setattr(panel, '_toe_version', lambda: '1.1.1')
    monkeypatch.setattr(panel, '_latest_release', lambda: None)
    dialogs, installs, rechecks = [], [], []

    def show(title, text, buttons):
        dialogs.append((text, buttons))
        return 0

    monkeypatch.setattr(panel, 'ui', SimpleNamespace(messageBox=show), raising=False)
    monkeypatch.setattr(panel, 'InstallAudioSupport', lambda **kw: installs.append(kw))
    monkeypatch.setattr(panel, 'AudioSupportStatus', lambda: rechecks.append(True))
    panel.ShowSetupDialog()
    text, buttons = dialogs[0]
    assert f'AUDIO SUPPORT:  {label}' in text
    assert 'Re-check' in buttons
    if state not in ('ready', 'checking'):
        assert report['error'] in text
        assert installs == [dict(support=report)]
    else:
        assert rechecks == [True]
        assert not installs


def test_mtime_change_revalidates_same_size_binary(controller, monkeypatch, tmp_path):
    path = executable(tmp_path)
    monkeypatch.setattr(controller, '_ffmpeg_candidates', lambda: iter([('download', path)]))
    calls = []
    monkeypatch.setattr(controller, '_ffmpeg_probe',
                        lambda path: calls.append(path) or ffmpeg_report(path))
    discovery = controller._FFmpegDiscovery()
    scan(discovery)
    stat = os.stat(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
    scan(discovery)
    assert calls == [path, path]


def test_panel_and_job_select_first_capable_binary(controller, monkeypatch, tmp_path):
    first, second = executable(tmp_path, 'limited'), executable(tmp_path, 'full')
    monkeypatch.setattr(controller, '_ffmpeg_candidates',
                        lambda: iter([('package', first), ('Homebrew', second)]))

    def probe(path):
        report = ffmpeg_report(path)
        if path == first:
            report['encoders'] -= {'libopus'}
        return report

    monkeypatch.setattr(controller, '_ffmpeg_probe', probe)
    discovery = controller._FFmpegDiscovery()
    snapshot = settle(discovery)
    ext = object.__new__(controller.VconExt)
    ext._ffmpeg_preferences = {}
    ext._ffmpeg_discovery = discovery
    ext._ffmpeg_policy = ('Automatic', '', True)
    monkeypatch.delenv('VCON_FFMPEG', raising=False)
    ext._audio_support = snapshot
    panel = ext.FFmpegStatus(audio='opus', extension='.webm', audio_sep='wav16')
    assert panel['state'] == 'ready'
    assert panel['path'] == ext._find_ffmpeg('opus', '.webm') == second
    assert panel['sidecar_path'] == ext._find_ffmpeg(audio_sep='wav16') == first
    discovery._checked_at = float('-inf')
    assert discovery.status()['state'] == 'ready'


def test_recheck_shows_completed_dialog_once(panel, monkeypatch):
    states = iter(['checking', 'checking', 'invalid'])
    monkeypatch.setattr(panel, '_ffmpeg_status', lambda **kw: {'state': next(states)})
    monkeypatch.setattr(panel, 'widget', lambda _: SimpleNamespace(par=SimpleNamespace(
        **{f'Buttonofffacecolor{c}': SimpleNamespace(val=0) for c in 'rgb'})))
    monkeypatch.setattr(panel, 'absTime', SimpleNamespace(frame=1), raising=False)
    dialogs = []
    monkeypatch.setattr(panel, 'ShowSetupDialog', lambda: dialogs.append(True))
    panel.AudioSupportStatus()
    panel._update_health_button()
    assert not dialogs
    panel._update_health_button()
    panel._update_health_button()
    assert dialogs == [True]


def test_shared_layout_and_opt_out(controller, tmp_path, monkeypatch):
    monkeypatch.setattr(controller, '_vcon_data_dir', lambda: str(tmp_path / 'vCon'))
    for tool in ('LTCfileGen', 'TDTools'):
        folder = tmp_path / tool / 'pylibs/imageio_ffmpeg/binaries'
        folder.mkdir(parents=True)
        executable(folder, 'ffmpeg-test')
    shared = [(src, path) for src, path in controller._ffmpeg_candidates()
              if src in ('TDTools', 'LTCfileGen')]
    assert [src for src, _ in shared] == ['TDTools', 'LTCfileGen']
    monkeypatch.setattr(controller, '_ffmpeg_candidates', lambda: iter(shared))
    monkeypatch.setattr(controller, '_ffmpeg_probe', ffmpeg_report)
    assert scan(controller._FFmpegDiscovery())['source'] == 'TDTools'
    assert scan(controller._FFmpegDiscovery(shared=False))['state'] == 'missing'


def test_saved_source_and_environment_override(controller, tmp_path, monkeypatch):
    import json
    good = executable(tmp_path, 'good')
    bad = executable(tmp_path, 'broken')
    monkeypatch.setattr(controller, '_vcon_data_dir', lambda: str(tmp_path))
    (tmp_path / 'panel_settings.json').write_text(json.dumps({'ffmpeg': {'source': 'Homebrew'}}))
    monkeypatch.setattr(controller, '_ffmpeg_candidates',
                        lambda: iter([('vCon download', good), ('Homebrew', bad)]))
    def probe(path):
        if path == bad:
            raise ValueError('wrong architecture')
        return ffmpeg_report(path)
    monkeypatch.setattr(controller, '_ffmpeg_probe', probe)
    ext = object.__new__(controller.VconExt)
    def report():
        ext.FFmpegStatus()
        return settle(ext._ffmpeg_discovery)
    monkeypatch.delenv('VCON_FFMPEG', raising=False)
    assert 'wrong architecture' in report()['error']
    monkeypatch.setenv('VCON_FFMPEG', good)
    assert report()['path'] == good
    monkeypatch.setenv('VCON_FFMPEG', str(tmp_path / 'missing'))
    assert 'VCON_FFMPEG' in report()['error']
    monkeypatch.delenv('VCON_FFMPEG')
    ext.SetFFmpegPreferences({'source': 'Custom', 'path': good})
    assert report()['source'] == 'Custom'


@pytest.mark.parametrize('choice,started,video_only', [(0, True, False), (1, True, True),
                                                         (2, False, False), (-1, False, False)])
def test_audio_start_choices(panel, monkeypatch, choice, started, video_only):
    panel._queue = [{'status': 'queued'}]
    states = iter([{'state': 'checking'}, {'state': 'invalid', 'error': 'bad build'}])
    monkeypatch.setattr(panel, '_ffmpeg_status', lambda: next(states))
    monkeypatch.setattr(panel, '_refresh_queue', lambda: None)
    monkeypatch.setattr(panel, '_queued_may_have_audio', lambda: True)
    monkeypatch.setattr(panel, '_val', {'audio_dd': 'none', 'audio_sep_t': True}.get)
    monkeypatch.setattr(panel, 'ui', SimpleNamespace(messageBox=lambda *a, **kw: choice),
                        raising=False)
    monkeypatch.setattr(panel, 'InstallAudioSupport',
                        lambda **kw: setattr(panel, '_install', {'running': True}))
    panel.Start()
    assert panel._start_pending and not panel._batch_started
    panel.Start()
    assert panel._batch_started is started
    assert panel._batch_video_only is video_only
    assert not panel._start_pending


def test_source_menu_persists_found_source_with_widget_settings(controller, panel, tmp_path,
                                                                monkeypatch):
    import json
    ext = object.__new__(controller.VconExt)
    ext._ffmpeg_preferences = {}
    monkeypatch.setattr(panel, 'ext', lambda: ext)
    monkeypatch.setattr(panel, '_SETTINGS_PATH', str(tmp_path / 'panel_settings.json'))
    widget = SimpleNamespace(par=SimpleNamespace(Value0=SimpleNamespace(eval=lambda: 'copy')))
    monkeypatch.setattr(panel, 'widget', lambda name: widget if name == 'audio_dd' else None)
    inventory = {**ffmpeg_report('/found'), 'source': 'TDTools', 'version': '8.0'}
    reports = iter([{'state': 'checking'}, inventory, inventory])
    monkeypatch.setattr(ext, 'FFmpegSources', lambda: next(reports))
    actions = iter(['TDTools (8.0)', 'Turn sharing off'])
    def choose(title, text, buttons):
        assert not any('Homebrew' in button for button in buttons)
        return buttons.index(next(actions))
    monkeypatch.setattr(panel, 'ui', SimpleNamespace(messageBox=choose), raising=False)
    monkeypatch.setattr(panel, 'AudioSupportStatus', lambda: None)
    panel._choose_ffmpeg_source()
    assert panel._source_menu_pending
    panel._choose_ffmpeg_source()
    assert not panel._source_menu_pending
    panel._choose_ffmpeg_source()
    saved = json.loads(Path(panel._SETTINGS_PATH).read_text())
    assert saved['audio_dd'] == 'copy'
    assert saved['ffmpeg'] == {'source': 'TDTools', 'path': '', 'shared': False}


def _atom(kind, body=b''):
    import struct
    return struct.pack('>I', 8 + len(body)) + kind + body


def _movie(path, *handlers):
    traks = b''.join(
        _atom(b'trak', _atom(b'mdia', _atom(b'hdlr', bytes(8) + h + bytes(12))))
        for h in handlers)
    path.write_bytes(_atom(b'ftyp', b'qt  ') + _atom(b'moov', traks))
    return str(path)


def test_movie_has_audio_reads_track_handlers(controller, tmp_path):
    assert controller.movie_has_audio(_movie(tmp_path / 'av.mov', b'vide', b'soun')) is True
    assert controller.movie_has_audio(_movie(tmp_path / 'v.mov', b'vide')) is False
    other = tmp_path / 'clip.mkv'
    other.write_bytes(b'\x1aE\xdf\xa3' + bytes(64))
    assert controller.movie_has_audio(str(other)) is None
    assert controller.movie_has_audio(str(tmp_path / 'gone.mov')) is None
    ext = object.__new__(controller.VconExt)
    assert ext.SourceMayHaveAudio(str(tmp_path / 'v.mov')) is False
    assert ext.SourceMayHaveAudio(str(other)) is True
    assert ext.SourceMayHaveAudio(None) is True


def test_status_reports_the_selection(controller, tmp_path, monkeypatch):
    monkeypatch.setattr(controller, '_vcon_data_dir', lambda: str(tmp_path))
    monkeypatch.setattr(controller, '_ffmpeg_candidates', lambda: iter(()))
    ext = object.__new__(controller.VconExt)
    monkeypatch.delenv('VCON_FFMPEG', raising=False)
    assert ext.FFmpegStatus()['selection'] == 'Automatic'
    ext.SetFFmpegPreferences({'source': 'Homebrew'})
    assert ext.FFmpegStatus(audio='copy')['selection'] == 'Homebrew'
    monkeypatch.setenv('VCON_FFMPEG', str(tmp_path / 'ffmpeg'))
    assert ext.FFmpegStatus()['selection'] == 'VCON_FFMPEG'


def test_start_offers_source_menu_not_install_for_a_pinned_source(panel, monkeypatch):
    panel._queue = [{'status': 'queued', 'input': '/clip.mov'}]
    monkeypatch.setattr(panel, '_ffmpeg_status', lambda: {
        'state': 'missing', 'error': 'Homebrew: ffmpeg not found', 'selection': 'Homebrew'})
    monkeypatch.setattr(panel, '_queued_may_have_audio', lambda: True)
    monkeypatch.setattr(panel, '_val', {'audio_dd': 'copy'}.get)
    shown, menus, installs = [], [], []
    def box(title, text, buttons):
        shown.append((text, buttons))
        return 0
    monkeypatch.setattr(panel, 'ui', SimpleNamespace(messageBox=box), raising=False)
    monkeypatch.setattr(panel, '_choose_ffmpeg_source', lambda: menus.append(True))
    monkeypatch.setattr(panel, 'InstallAudioSupport', lambda **kw: installs.append(True))
    panel.Start()
    assert shown[0][1] == ['FFmpeg source…', 'Continue video only', 'Cancel']
    assert "chosen FFmpeg source can't be used" in shown[0][0]
    assert menus == [True] and not installs and not panel._batch_started


def test_start_skips_the_prompt_for_silent_clips(panel, monkeypatch):
    panel._queue = [{'status': 'queued', 'input': '/silent.mov'}]
    monkeypatch.setattr(panel, 'ext', lambda: SimpleNamespace(SourceMayHaveAudio=lambda p: False))
    monkeypatch.setattr(panel, '_ffmpeg_status', lambda: pytest.fail('no check needed'))
    monkeypatch.setattr(panel, '_refresh_queue', lambda: None)
    monkeypatch.setattr(panel, '_val', {'audio_dd': 'copy'}.get)
    monkeypatch.setattr(panel, 'ui', SimpleNamespace(
        messageBox=lambda *a, **kw: pytest.fail('no prompt for silent clips')), raising=False)
    panel.Start()
    assert panel._batch_started and not panel._batch_video_only


@pytest.mark.parametrize('selection,offered', [('Automatic', True), ('vCon download', True),
                                               ('Homebrew', False), ('Custom', False),
                                               ('VCON_FFMPEG', False)])
def test_setup_dialog_offers_install_only_when_it_can_help(panel, monkeypatch, selection,
                                                          offered):
    monkeypatch.setattr(panel, '_ffmpeg_status', lambda: {
        'state': 'missing', 'path': None, 'error': 'not found', 'selection': selection})
    for name, value in (('_python_for_pip', None), ('_cli_version', None),
                        ('_toe_version', '1.1.1'), ('_latest_release', None)):
        monkeypatch.setattr(panel, name, lambda *a, value=value, **kw: value)
    seen = []
    def box(title, text, buttons):
        seen.append(buttons)
        return buttons.index('Close')
    monkeypatch.setattr(panel, 'ui', SimpleNamespace(messageBox=box), raising=False)
    panel.ShowSetupDialog()
    assert ('Install Now' in seen[0]) is offered


def test_probe_timeout_is_retried_not_cached(controller, tmp_path, monkeypatch):
    path = executable(tmp_path)
    monkeypatch.setattr(controller, '_ffmpeg_candidates', lambda: iter([('vCon download', path)]))
    calls = []
    def probe(p):
        calls.append(p)
        if len(calls) == 1:
            raise controller._ProbeTimeout('-version timed out after 15 seconds')
        return ffmpeg_report(p)
    monkeypatch.setattr(controller, '_ffmpeg_probe', probe)
    discovery = controller._FFmpegDiscovery()
    assert 'timed out' in scan(discovery)['error']
    assert scan(discovery)['state'] == 'ready'
    assert scan(discovery)['state'] == 'ready' and len(calls) == 2
