"""Stack/framework detection, verification defaults, and polyglot context helpers."""

import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

IGNORE_DIRS = {'.git','.vibe','.agents','.claude','.hg','.svn','.idea','.vscode','.tox','.nox','.mypy_cache','.pytest_cache','.ruff_cache','.venv','venv','env','__pycache__','node_modules','dist','build','coverage','.next','.nuxt','target','vendor'}


def _text(path: Path) -> str:
    try: return path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError): return ''


def _json(path: Path) -> Dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError): return {}


def _walk(root: Path, suffixes: Optional[Set[str]] = None) -> Iterable[Path]:
    for current, dirs, files in os.walk(str(root)):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for name in files:
            p = Path(current) / name
            if not p.is_symlink() and (suffixes is None or p.suffix.lower() in suffixes):
                yield p


def _deps(data: Dict[str, object], fields: Sequence[str]) -> Set[str]:
    out = set()
    for field in fields:
        value = data.get(field)
        if isinstance(value, dict): out.update(str(k).lower() for k in value)
    return out


def _python_text(root: Path) -> str:
    names = ['pyproject.toml','requirements.txt','requirements-dev.txt','requirements/base.txt','requirements/dev.txt','Pipfile']
    return '\n'.join(_text(root / n).lower() for n in names)


def _ruby_text(root: Path) -> str:
    texts = [_text(root / name).lower() for name in ('Gemfile', 'Gemfile.lock')]
    texts.extend(_text(path).lower() for path in sorted(root.glob('*.gemspec')))
    return '\n'.join(texts)


def detect_stack(root: Path) -> Dict[str, object]:
    markers = {
        'python':['pyproject.toml','requirements.txt','setup.py','setup.cfg','Pipfile'],
        'javascript':['package.json'], 'typescript':['tsconfig.json'], 'php':['composer.json','wp-config.php'],
        'java':['pom.xml','build.gradle','build.gradle.kts'], 'go':['go.mod'], 'rust':['Cargo.toml'],
        'ruby':['Gemfile','Gemfile.lock','Rakefile','.ruby-version'], 'dotnet':['global.json'],
    }
    found = {k:[n for n in v if (root/n).exists()] for k,v in markers.items()}
    found = {k:v for k,v in found.items() if v}
    root_ruby = sorted([p.name for p in root.glob('*.rb') if p.is_file()] + [p.name for p in root.glob('*.gemspec') if p.is_file()])
    if 'ruby' not in found and root_ruby: found['ruby'] = root_ruby
    root_php = sorted(p.name for p in root.glob('*.php') if p.is_file())
    style_text = _text(root/'style.css')
    plugin_header = any(re.search(r'(?mi)^\s*Plugin Name\s*:', _text(root/name)) for name in root_php)
    theme_header = bool(re.search(r'(?mi)^\s*Theme Name\s*:', style_text))
    standalone_wordpress = plugin_header or theme_header
    if ('php' not in found) and ((root/'wp-content').exists() or standalone_wordpress or root_php):
        found['php'] = root_php or ['wp-content']
    order = ['typescript','javascript','python','php','ruby','java','go','rust','dotnet']
    primary = next((x for x in order if x in found), sorted(found)[0] if found else 'generic')
    frameworks, evidence = [], {}
    py = _python_text(root)
    for name in ('flask','fastapi','django'):
        if re.search(r'(^|[^a-z0-9_-])'+re.escape(name)+r'([^a-z0-9_-]|$)', py) or (name=='django' and (root/'manage.py').exists()):
            frameworks.append(name); evidence[name] = ['python dependency or framework marker']
    pkg = _deps(_json(root/'package.json'), ['dependencies','devDependencies','peerDependencies','optionalDependencies'])
    frontend_deps = [
        ('express','express'),
        ('@nestjs/core','nestjs'),
        ('next','nextjs'),
        ('nuxt','nuxt'),
        ('@sveltejs/kit','sveltekit'),
        ('react','react'),
        ('vue','vue'),
        ('svelte','svelte'),
        ('vite','vite'),
    ]
    for dep,name in frontend_deps:
        if dep in pkg:
            frameworks.append(name)
            evidence[name] = ['package dependency: '+dep]
    composer = _deps(_json(root/'composer.json'), ['require','require-dev'])
    if 'laravel/framework' in composer or (root/'artisan').exists(): frameworks.append('laravel'); evidence['laravel']=['laravel/framework or artisan']
    wordpress_composer = any(dep in composer for dep in ('johnpbloch/wordpress-core','roots/wordpress','wordpress/wordpress'))
    wordpress_marker = (root/'wp-config.php').exists() or (root/'wp-content').exists() or standalone_wordpress
    if wordpress_composer or wordpress_marker:
        frameworks.append('wordpress')
        evidence['wordpress']=['WordPress core/composer dependency, wp-config.php/wp-content marker, or plugin/theme header']
    ruby = _ruby_text(root)
    rails_dependency = bool(re.search(r'''(?mi)^\s*gem\s+["']rails["']''', ruby) or re.search(r'(?mi)^\s+rails\s+\(', ruby))
    rails_marker = (root/'bin'/'rails').exists() or ((root/'config'/'application.rb').exists() and (root/'config'/'routes.rb').exists())
    if rails_dependency or rails_marker:
        frameworks.append('rails'); evidence['rails']=['rails gem or Rails application marker']
        if 'ruby' not in found: found['ruby'] = ['Rails application marker']
        primary = 'ruby'
    java = '\n'.join(_text(root/n).lower() for n in ['pom.xml','build.gradle','build.gradle.kts'])
    if 'spring-boot' in java or 'org.springframework' in java: frameworks.append('spring'); evidence['spring']=['Spring dependency']
    gomod = _text(root/'go.mod').lower()
    if 'github.com/gin-gonic/gin' in gomod: frameworks.append('gin'); evidence['gin']=['go module gin']
    if 'github.com/gofiber/fiber' in gomod: frameworks.append('fiber'); evidence['fiber']=['go module fiber']
    cargo = _text(root/'Cargo.toml').lower()
    if re.search(r'(?m)^\s*actix-web\s*=', cargo): frameworks.append('actix-web'); evidence['actix-web']=['Cargo dependency actix-web']
    return {'primary':primary,'languages':list(found) or ['generic'],'frameworks':list(dict.fromkeys(frameworks)),'markers':found,'framework_evidence':evidence}


def discover_verification_commands(root: Path) -> List[List[str]]:
    commands = []
    package = _json(root/'package.json'); scripts = package.get('scripts') or {}
    if isinstance(scripts, dict):
        runner = ['pnpm','run'] if (root/'pnpm-lock.yaml').exists() else (['yarn'] if (root/'yarn.lock').exists() else ['npm','run'])
        for name in ('lint','typecheck','test','build'):
            if name in scripts: commands.append(runner+[name])
    py = _python_text(root)
    if py:
        if 'ruff' in py: commands.append(['python','-m','ruff','check','.'])
        if 'pyright' in py: commands.append(['pyright'])
        elif 'mypy' in py: commands.append(['python','-m','mypy','.'])
        if 'pytest' in py: commands.append(['python','-m','pytest','-q'])
    if (root/'manage.py').exists():
        commands.append(['python','manage.py','check'])
        if 'pytest' not in py:
            commands.append(['python','manage.py','test'])
    stack = detect_stack(root); ruby = _ruby_text(root)
    if 'ruby' in (stack.get('languages') or []):
        if re.search(r'''(?mi)^\s*gem\s+["']rubocop(?:-rails)?["']''', ruby): commands.append(['bundle','exec','rubocop'])
        has_rspec = bool(re.search(r'''(?mi)^\s*gem\s+["'](?:rspec|rspec-rails)["']''', ruby) or (root/'.rspec').exists())
        if has_rspec: commands.append(['bundle','exec','rspec'])
        elif 'rails' in (stack.get('frameworks') or []): commands.append(['bundle','exec','rails','test'])
    composer = _json(root/'composer.json'); comptext = json.dumps(composer).lower() if composer else ''
    if composer:
        scripts = composer.get('scripts') or {}
        if isinstance(scripts, dict):
            for name in ('lint','analyse','analyze','test'):
                if name in scripts: commands.append(['composer','run',name])
        if 'phpstan/phpstan' in comptext or 'nunomaduro/larastan' in comptext: commands.append(['php','vendor/bin/phpstan','analyse'])
        if 'pestphp/pest' in comptext: commands.append(['php','vendor/bin/pest'])
        elif 'phpunit/phpunit' in comptext: commands.append(['php','vendor/bin/phpunit'])
        elif (root/'artisan').exists(): commands.append(['php','artisan','test'])
    if (root/'pom.xml').exists():
        mvn = 'mvnw.cmd' if os.name == 'nt' and (root/'mvnw.cmd').exists() else ('./mvnw' if (root/'mvnw').exists() else 'mvn')
        commands.append([mvn,'test'])
    elif (root/'build.gradle').exists() or (root/'build.gradle.kts').exists():
        gradle = 'gradlew.bat' if os.name == 'nt' and (root/'gradlew.bat').exists() else ('./gradlew' if (root/'gradlew').exists() else 'gradle')
        commands.append([gradle,'test'])
    if (root/'go.mod').exists(): commands.append(['go','test','./...'])
    if (root/'Cargo.toml').exists(): commands.extend([['cargo','check'],['cargo','test']])
    out=[]; seen=set()
    for c in commands:
        t=tuple(c)
        if t not in seen: seen.add(t); out.append(c)
    return out


def effective_adapter(root: Path) -> Dict[str, object]:
    stack = detect_stack(root)
    bases = [root/'.vibe'/'adapters', root/'adapters']
    base = next((candidate for candidate in bases if candidate.exists()), None)

    language = None
    frameworks = []
    if base is not None:
        language_path = base/'languages'/(str(stack.get('primary', 'generic')) + '.json')
        if language_path.exists():
            language = _json(language_path)
        for framework in stack.get('frameworks') or []:
            path = base/'frameworks'/(str(framework) + '.json')
            if path.exists():
                frameworks.append(_json(path))

    return {
        'stack': stack,
        'language': language or {'id': stack.get('primary', 'generic'), 'kind': 'language'},
        'frameworks': frameworks,
        'adapter_source': str(base) if base is not None else None,
    }


PHP_NAMESPACE_RE=re.compile(r'\bnamespace\s+([^;]+);')
PHP_CLASS_RE=re.compile(r'\b(?:class|interface|trait|enum)\s+([A-Za-z_][A-Za-z0-9_]*)')
PHP_USE_RE=re.compile(r'^\s*use\s+([^;{]+);',re.MULTILINE)
PHP_REQ_RE=re.compile(r'(?:require|require_once|include|include_once)\s*\(?\s*(?:__DIR__\s*\.\s*)?[\'"]([^\'"]+)[\'"]',re.I)
JAVA_PACKAGE_RE=re.compile(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;?',re.M)
JAVA_IMPORT_RE=re.compile(r'^\s*import\s+(?:static\s+)?([A-Za-z0-9_.*]+)\s*;?',re.M)
GO_SINGLE_RE=re.compile(r'^\s*import\s+(?:[A-Za-z0-9_.]+\s+)?"([^"]+)"',re.M)
GO_BLOCK_RE=re.compile(r'import\s*\((.*?)\)',re.S)
GO_LINE_RE=re.compile(r'(?:[A-Za-z0-9_.]+\s+)?"([^"]+)"')
RUST_MOD_RE=re.compile(r'^\s*(?:pub\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;',re.M)
RUST_USE_RE=re.compile(r'^\s*(?:pub\s+)?use\s+crate::([^;{]+)',re.M)
RUBY_REQUIRE_RELATIVE_RE=re.compile(r'''^\s*require_relative\s*\(?\s*["']([^"']+)["']\s*\)?''',re.M)
RUBY_REQUIRE_RE=re.compile(r'''^\s*require\s*\(?\s*["']([^"']+)["']\s*\)?''',re.M)


def scan_php_dependencies(root: Path, files: Sequence[Path]) -> Tuple[Set[str],Set[Tuple[str,str]]]:
    items=[p for p in files if p.suffix.lower()=='.php']; nodes={p.relative_to(root).as_posix() for p in items}; edges=set(); classes={}
    for p in items:
        text=_text(p); ns=PHP_NAMESPACE_RE.search(text); cls=PHP_CLASS_RE.search(text)
        if cls:
            full=((ns.group(1).strip('\\ ')+'\\') if ns else '')+cls.group(1); classes[full.lower()]=p.relative_to(root).as_posix()
    for p in items:
        src=p.relative_to(root).as_posix(); text=_text(p)
        for m in PHP_USE_RE.finditer(text):
            raw=m.group(1).strip()
            if '{' in raw or raw.lower().startswith(('function ','const ')): continue
            name=re.split(r'\s+as\s+',raw,flags=re.I)[0].strip('\\ '); dst=classes.get(name.lower())
            if dst and dst!=src: edges.add((src,dst))
        for m in PHP_REQ_RE.finditer(text):
            candidate=(p.parent/m.group(1).replace('\\','/')).resolve()
            try: rel=candidate.relative_to(root).as_posix()
            except ValueError: continue
            if candidate.exists() and candidate.is_file() and rel!=src: edges.add((src,rel))
    return nodes,edges


def scan_java_dependencies(root: Path, files: Sequence[Path]) -> Tuple[Set[str],Set[Tuple[str,str]]]:
    items=[p for p in files if p.suffix.lower() in {'.java','.kt','.kts'}]; nodes={p.relative_to(root).as_posix() for p in items}; edges=set(); classes={}
    for p in items:
        text=_text(p); m=JAVA_PACKAGE_RE.search(text); full=((m.group(1)+'.') if m else '')+p.stem; classes[full]=p.relative_to(root).as_posix()
    for p in items:
        src=p.relative_to(root).as_posix()
        for m in JAVA_IMPORT_RE.finditer(_text(p)):
            name=m.group(1).rstrip('.*'); probe=name; dst=None
            while probe and not dst: dst=classes.get(probe); probe=probe.rpartition('.')[0]
            if dst and dst!=src: edges.add((src,dst))
    return nodes,edges


def scan_go_dependencies(root: Path, files: Sequence[Path]) -> Tuple[Set[str],Set[Tuple[str,str]]]:
    items=[p for p in files if p.suffix.lower()=='.go']; nodes={p.relative_to(root).as_posix() for p in items}; edges=set(); module=''
    for line in _text(root/'go.mod').splitlines():
        if line.strip().startswith('module '): module=line.strip().split(None,1)[1]; break
    if not module: return nodes,edges
    grouped=defaultdict(list)
    for p in items: grouped[p.parent.relative_to(root).as_posix()].append(p)
    reps={}
    for rel,ps in grouped.items():
        imp=module if rel=='.' else module.rstrip('/')+'/'+rel; chosen=sorted([p for p in ps if not p.name.endswith('_test.go')] or ps)[0]; reps[imp]=chosen.relative_to(root).as_posix()
    for p in items:
        src=p.relative_to(root).as_posix(); text=_text(p); imports=set(GO_SINGLE_RE.findall(text))
        for block in GO_BLOCK_RE.findall(text): imports.update(GO_LINE_RE.findall(block))
        for imp in imports:
            dst=reps.get(imp)
            if dst and dst!=src: edges.add((src,dst))
    return nodes,edges


def scan_rust_dependencies(root: Path, files: Sequence[Path]) -> Tuple[Set[str],Set[Tuple[str,str]]]:
    items=[p for p in files if p.suffix.lower()=='.rs']; nodes={p.relative_to(root).as_posix() for p in items}; edges=set(); modules={}
    for p in items:
        rel=p.relative_to(root); parts=list(rel.parts); parts=parts[1:] if parts and parts[0]=='src' else parts
        if not parts: continue
        if parts[-1] in ('lib.rs','main.rs'): key=''
        elif parts[-1]=='mod.rs': key='::'.join(parts[:-1])
        else: parts[-1]=Path(parts[-1]).stem; key='::'.join(parts)
        modules[key]=rel.as_posix()
    for p in items:
        src=p.relative_to(root).as_posix(); text=_text(p); rel=p.relative_to(root); parts=list(rel.parts); parts=parts[1:] if parts and parts[0]=='src' else parts
        base=[] if not parts or parts[-1] in ('lib.rs','main.rs') else parts[:-1]
        for m in RUST_MOD_RE.finditer(text):
            dst=modules.get('::'.join(base+[m.group(1)]))
            if dst and dst!=src: edges.add((src,dst))
        for m in RUST_USE_RE.finditer(text):
            probe=m.group(1).strip().split('::{',1)[0].rstrip(':'); dst=None
            while probe and not dst: dst=modules.get(probe); probe=probe.rpartition('::')[0]
            if dst and dst!=src: edges.add((src,dst))
    return nodes,edges


def scan_ruby_dependencies(root: Path, files: Sequence[Path]) -> Tuple[Set[str],Set[Tuple[str,str]]]:
    items=[p for p in files if p.suffix.lower()=='.rb']; nodes={p.relative_to(root).as_posix() for p in items}; edges=set(); require_map={}; resolved_root=root.resolve()
    for p in items:
        rel=p.relative_to(root).as_posix(); key=rel[:-3] if rel.endswith('.rb') else rel; require_map[key]=rel
        if key.startswith('lib/'): require_map[key[4:]]=rel
    for p in items:
        src=p.relative_to(root).as_posix(); text=_text(p)
        for m in RUBY_REQUIRE_RELATIVE_RE.finditer(text):
            candidate=p.parent/m.group(1)
            if not candidate.suffix: candidate=Path(str(candidate)+'.rb')
            candidate=candidate.resolve()
            try: rel=candidate.relative_to(resolved_root).as_posix()
            except ValueError: continue
            if candidate.is_file() and rel in nodes and rel!=src: edges.add((src,rel))
        for m in RUBY_REQUIRE_RE.finditer(text):
            key=m.group(1).replace('\\','/')
            if key.endswith('.rb'): key=key[:-3]
            dst=require_map.get(key.lstrip('./'))
            if dst and dst!=src: edges.add((src,dst))
    return nodes,edges


def scan_polyglot_dependencies(root: Path, files: Sequence[Path]) -> Tuple[Set[str],Set[Tuple[str,str]],List[str]]:
    nodes=set(); edges=set(); scanners=[]
    for name,fn in [('php-static',scan_php_dependencies),('java-kotlin-imports',scan_java_dependencies),('go-module-imports',scan_go_dependencies),('rust-mod-use',scan_rust_dependencies),('ruby-require',scan_ruby_dependencies)]:
        n,e=fn(root,files)
        if n: nodes.update(n); edges.update(e); scanners.append(name)
    return nodes,edges,scanners


PY_ROUTE_RE=re.compile(r'@\s*([A-Za-z_][A-Za-z0-9_.]*)\.(route|get|post|put|patch|delete|options|head)\s*\(\s*[\'"]([^\'"]+)[\'"]',re.I)
DJANGO_ROUTE_RE=re.compile(r'\b(?:path|re_path)\s*\(\s*[\'"]([^\'"]+)[\'"]')
EXPRESS_ROUTE_RE=re.compile(r'\b(?:app|router)\.(get|post|put|patch|delete|options|head|use)\s*\(\s*[\'"]([^\'"]+)[\'"]',re.I)
NEST_CONTROLLER_RE=re.compile(r'@Controller\s*\(\s*[\'"]?([^\'")]*?)[\'"]?\s*\)')
NEST_METHOD_RE=re.compile(r'@(Get|Post|Put|Patch|Delete|Options|Head|All)\s*\(\s*[\'"]?([^\'")]*?)[\'"]?\s*\)',re.I)
LARAVEL_ROUTE_RE=re.compile(r'Route::(get|post|put|patch|delete|options|any|match|resource|apiResource)\s*\(\s*[\'"]([^\'"]+)[\'"]',re.I)
SPRING_RE=re.compile(r'@(RequestMapping|GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping)\s*\(([^)]*)\)',re.M)
SPRING_PATH_RE=re.compile(r'(?:value\s*=\s*|path\s*=\s*)?[\'"]([^\'"]+)[\'"]')
GO_ROUTE_RE=re.compile(r'\b(?:[A-Za-z_][A-Za-z0-9_]*\.)?(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD|Get|Post|Put|Patch|Delete|Options|Head)\s*\(\s*["`]([^"`]+)["`]')
ACTIX_RE=re.compile(r'#\s*\[\s*(get|post|put|patch|delete|head)\s*\(\s*"([^"]+)"\s*\)\s*\]',re.I)
WORDPRESS_REST_RE=re.compile(r'register_rest_route\s*\(\s*[\'\"]([^\'\"]+)[\'\"]\s*,\s*[\'\"]([^\'\"]+)[\'\"]',re.I)
RAILS_HTTP_ROUTE_RE=re.compile(r'''^\s*(get|post|put|patch|delete|options|head|match)\s+\(?\s*["']([^"']+)["']''',re.M|re.I)
RAILS_RESOURCE_ROUTE_RE=re.compile(r'''^\s*(resources?)\s+(?::([A-Za-z_][A-Za-z0-9_]*)|["']([^"']+)["'])''',re.M|re.I)


def framework_context(root: Path, files: Optional[Sequence[Path]]=None) -> Dict[str,object]:
    stack=detect_stack(root); frameworks=list(stack.get('frameworks') or []); fs=list(files) if files is not None else list(_walk(root)); routes=[]; components={}
    def add_regex(framework,suffixes,pattern,method_group=None,path_group=1):
        for p in fs:
            if p.suffix.lower() not in suffixes: continue
            for m in pattern.finditer(_text(p)):
                method=(m.group(method_group).upper() if method_group else 'ROUTE'); routes.append({'framework':framework,'file':p.relative_to(root).as_posix(),'method':method,'path':m.group(path_group)})
    if 'flask' in frameworks: add_regex('flask',{'.py'},PY_ROUTE_RE,2,3); components['flask_blueprints']=[p.relative_to(root).as_posix() for p in fs if p.suffix=='.py' and 'Blueprint(' in _text(p)]
    if 'fastapi' in frameworks: add_regex('fastapi',{'.py'},PY_ROUTE_RE,2,3); components['fastapi_routers']=[p.relative_to(root).as_posix() for p in fs if p.suffix=='.py' and 'APIRouter(' in _text(p)]
    if 'django' in frameworks: add_regex('django',{'.py'},DJANGO_ROUTE_RE,None,1); components['django_apps']=sorted({p.relative_to(root).parts[0] for p in fs if p.name in ('models.py','apps.py','views.py') and len(p.relative_to(root).parts)>1})
    if 'express' in frameworks: add_regex('express',{'.js','.jsx','.ts','.tsx'},EXPRESS_ROUTE_RE,1,2)
    if 'nestjs' in frameworks:
        ctrls=[]
        for p in fs:
            if p.suffix.lower() not in {'.ts','.js'}: continue
            text=_text(p); c=NEST_CONTROLLER_RE.search(text)
            if c: ctrls.append({'file':p.relative_to(root).as_posix(),'base_path':c.group(1),'handlers':[{'method':m.group(1).upper(),'path':m.group(2)} for m in NEST_METHOD_RE.finditer(text)]})
        components['nestjs_controllers']=ctrls
    if 'react' in frameworks:
        components['react_components']=sorted(p.relative_to(root).as_posix() for p in fs if p.suffix.lower() in {'.jsx','.tsx'} and re.search(r'\b(?:function|const|class)\s+[A-Z][A-Za-z0-9_]*', _text(p)))
        components['react_hooks']=sorted(p.relative_to(root).as_posix() for p in fs if p.suffix.lower() in {'.js','.jsx','.ts','.tsx'} and re.search(r'\buse[A-Z][A-Za-z0-9_]*\s*\(', _text(p)))
    if 'vue' in frameworks or 'nuxt' in frameworks:
        components['vue_components']=sorted(p.relative_to(root).as_posix() for p in fs if p.suffix.lower()=='.vue')
        components['vue_composables']=sorted(p.relative_to(root).as_posix() for p in fs if 'composables' in p.relative_to(root).parts)
    if 'svelte' in frameworks or 'sveltekit' in frameworks:
        components['svelte_components']=sorted(p.relative_to(root).as_posix() for p in fs if p.suffix.lower()=='.svelte')
    if 'vite' in frameworks:
        components['vite_config']=sorted(p.relative_to(root).as_posix() for p in fs if p.name in ('vite.config.js','vite.config.ts','vite.config.mjs','vite.config.mts'))
    if 'nextjs' in frameworks:
        for p in fs:
            if p.suffix.lower() not in {'.js','.jsx','.ts','.tsx'}: continue
            rel=p.relative_to(root); parts=list(rel.parts)
            if parts and parts[0]=='app' and p.stem in ('page','route'):
                seg=[x for x in parts[1:-1] if not (x.startswith('(') and x.endswith(')'))]; routes.append({'framework':'nextjs','file':rel.as_posix(),'method':'FILE_ROUTE','path':'/'+('/'.join(seg)) if seg else '/'})
            elif parts and parts[0]=='pages' and p.stem not in ('_app','_document','_error'):
                seg=parts[1:]; seg[-1]=Path(seg[-1]).stem
                if seg[-1]=='index': seg=seg[:-1]
                routes.append({'framework':'nextjs','file':rel.as_posix(),'method':'FILE_ROUTE','path':'/'+('/'.join(seg)) if seg else '/'})
        components['nextjs_client_components']=sorted(p.relative_to(root).as_posix() for p in fs if p.suffix.lower() in {'.js','.jsx','.ts','.tsx'} and _text(p).lstrip().startswith(("'use client'","\"use client\"")))
    if 'nuxt' in frameworks:
        for p in fs:
            rel=p.relative_to(root); parts=list(rel.parts)
            if p.suffix.lower()=='.vue' and parts and parts[0]=='pages':
                seg=list(parts[1:]); seg[-1]=Path(seg[-1]).stem
                if seg[-1]=='index': seg=seg[:-1]
                routes.append({'framework':'nuxt','file':rel.as_posix(),'method':'FILE_ROUTE','path':'/'+('/'.join(seg)) if seg else '/'})
        components['nuxt_server_routes']=sorted(p.relative_to(root).as_posix() for p in fs if len(p.relative_to(root).parts)>=3 and p.relative_to(root).parts[:2]==('server','api'))
    if 'sveltekit' in frameworks:
        for p in fs:
            rel=p.relative_to(root); parts=list(rel.parts)
            if 'routes' in parts and p.name.startswith('+page'):
                idx=parts.index('routes'); seg=[x for x in parts[idx+1:-1]]
                routes.append({'framework':'sveltekit','file':rel.as_posix(),'method':'FILE_ROUTE','path':'/'+('/'.join(seg)) if seg else '/'})
        components['sveltekit_server_files']=sorted(p.relative_to(root).as_posix() for p in fs if p.name.startswith(('+server','+page.server','+layout.server')))
    if 'wordpress' in frameworks:
        plugin_files=[]; theme_files=[]; hooks=[]; rest_routes=[]
        for p in fs:
            rel=p.relative_to(root); parts=rel.parts
            if len(parts)>=3 and parts[0]=='wp-content' and parts[1]=='plugins': plugin_files.append(rel.as_posix())
            if len(parts)>=3 and parts[0]=='wp-content' and parts[1]=='themes': theme_files.append(rel.as_posix())
            if p.suffix.lower()=='.php':
                text=_text(p)
                if re.search(r'\b(add_action|add_filter|add_shortcode)\s*\(', text): hooks.append(rel.as_posix())
                for m in WORDPRESS_REST_RE.finditer(text):
                    rest_routes.append({'framework':'wordpress','file':rel.as_posix(),'method':'REST_ROUTE','path':'/'+m.group(1).strip('/')+'/'+m.group(2).lstrip('/')})
        components['wordpress_plugins']=sorted(plugin_files)
        components['wordpress_themes']=sorted(theme_files)
        components['wordpress_hook_files']=sorted(hooks)
        routes.extend(rest_routes)
    if 'rails' in frameworks:
        for p in fs:
            rel=p.relative_to(root)
            if p.suffix.lower()=='.rb' and rel.as_posix()=='config/routes.rb':
                text=_text(p)
                for m in RAILS_HTTP_ROUTE_RE.finditer(text): routes.append({'framework':'rails','file':rel.as_posix(),'method':m.group(1).upper(),'path':m.group(2)})
                for m in RAILS_RESOURCE_ROUTE_RE.finditer(text):
                    name=m.group(2) or m.group(3); routes.append({'framework':'rails','file':rel.as_posix(),'method':m.group(1).upper(),'path':'/'+name.strip('/')})
        for label,prefix in [('rails_controllers',('app','controllers')),('rails_models',('app','models')),('rails_services',('app','services')),('rails_jobs',('app','jobs')),('rails_mailers',('app','mailers')),('rails_policies',('app','policies')),('rails_channels',('app','channels')),('rails_migrations',('db','migrate'))]:
            components[label]=sorted(p.relative_to(root).as_posix() for p in fs if p.suffix.lower()=='.rb' and p.relative_to(root).parts[:len(prefix)]==prefix)
    if 'laravel' in frameworks:
        for p in fs:
            rel=p.relative_to(root)
            if p.suffix.lower()=='.php' and rel.parts and rel.parts[0]=='routes':
                for m in LARAVEL_ROUTE_RE.finditer(_text(p)): routes.append({'framework':'laravel','file':rel.as_posix(),'method':m.group(1).upper(),'path':m.group(2)})
        for label,name in [('laravel_controllers','Controllers'),('laravel_models','Models'),('laravel_middleware','Middleware'),('laravel_providers','Providers'),('laravel_jobs','Jobs')]: components[label]=sorted(p.relative_to(root).as_posix() for p in fs if name.lower() in [x.lower() for x in p.relative_to(root).parts])
    if 'spring' in frameworks:
        comps=[]
        for p in fs:
            if p.suffix.lower() not in {'.java','.kt','.kts'}: continue
            text=_text(p)
            if any(x in text for x in ('@RestController','@Controller','@Service','@Repository','@Component')): comps.append(p.relative_to(root).as_posix())
            for m in SPRING_RE.finditer(text):
                pm=SPRING_PATH_RE.search(m.group(2)); routes.append({'framework':'spring','file':p.relative_to(root).as_posix(),'method':m.group(1).replace('Mapping','').upper() or 'REQUEST','path':pm.group(1) if pm else ''})
        components['spring_components']=sorted(comps)
    if 'gin' in frameworks or 'fiber' in frameworks:
        fw='gin' if 'gin' in frameworks else 'fiber'
        for p in fs:
            if p.suffix.lower()=='.go':
                for m in GO_ROUTE_RE.finditer(_text(p)): routes.append({'framework':fw,'file':p.relative_to(root).as_posix(),'method':m.group(1).upper(),'path':m.group(2)})
    if 'actix-web' in frameworks: add_regex('actix-web',{'.rs'},ACTIX_RE,1,2)
    return {'frameworks':frameworks,'routes':sorted(routes,key=lambda x:(x['framework'],x['file'],x['path'],x['method'])),'components':components,'notes':['Static best-effort context; dynamic registration, DI, reflection, generated routes and macros may require native tooling.']}
