<?php
// CLI only: there is no web path to creating the first admin, on purpose.
//   php lib/admin.php create-admin <name>
//   php lib/admin.php passwd <name>
//   php lib/admin.php list

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}

require_once __DIR__ . '/db.php';

function prompt_password(): string
{
    if (function_exists('readline')) {
        echo 'Password: ';
        system('stty -echo 2>/dev/null');
        $p = trim((string) fgets(STDIN));
        system('stty echo 2>/dev/null');
        echo "\n";
        return $p;
    }
    return trim((string) fgets(STDIN));
}

$cmd  = $argv[1] ?? '';
$name = $argv[2] ?? '';

switch ($cmd) {
    case 'create-admin':
    case 'create-user':
        if ($name === '') {
            fwrite(STDERR, "usage: php lib/admin.php $cmd <name>\n");
            exit(1);
        }
        $pass = prompt_password();
        if (strlen($pass) < 4) {
            fwrite(STDERR, "password too short\n");
            exit(1);
        }
        $admin = $cmd === 'create-admin' ? 1 : 0;
        q('INSERT INTO users (name, pass_hash, is_admin) VALUES (?, ?, ?)',
          [$name, password_hash($pass, PASSWORD_DEFAULT), $admin]);
        echo "created $name" . ($admin ? " (admin)\n" : "\n");
        break;

    case 'passwd':
        if ($name === '') {
            fwrite(STDERR, "usage: php lib/admin.php passwd <name>\n");
            exit(1);
        }
        $pass = prompt_password();
        q('UPDATE users SET pass_hash = ? WHERE name = ?',
          [password_hash($pass, PASSWORD_DEFAULT), $name]);
        echo "password set for $name\n";
        break;

    case 'list':
        foreach (all('SELECT id, name, is_admin FROM users ORDER BY id') as $u) {
            printf("%3d  %-20s %s\n", $u['id'], $u['name'], $u['is_admin'] ? 'admin' : '');
        }
        break;

    default:
        fwrite(STDERR, "commands: create-admin <name> | create-user <name> | passwd <name> | list\n");
        exit(1);
}
