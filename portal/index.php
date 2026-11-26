<?php
require_once __DIR__ . '/lib/db.php';
require_once __DIR__ . '/lib/auth.php';
require_once __DIR__ . '/lib/slots.php';

$csrf = csrf_token();          // mints the cookie before anything can POST
$user = current_user();
$admin = is_admin($user);

function h(?string $s): string
{
    return htmlspecialchars((string) $s, ENT_QUOTES, 'UTF-8');
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LAN Party</title>
<link rel="stylesheet" href="assets/app.css">
</head>
<body>
<?php if (!$user): ?>

<form class="login" method="post" onsubmit="return doLogin(event)">
    <h1>LAN Party</h1>
    <p class="hint">This device is not recognised yet. Sign in once and it will remember you.</p>
    <input name="name" placeholder="name" autocomplete="username" autofocus required>
    <input name="pass" type="password" placeholder="password" autocomplete="current-password" required>
    <button>Sign in</button>
    <p class="err" id="err"></p>
</form>
<script>
const CSRF = <?= json_encode($csrf) ?>;
async function doLogin(e) {
    e.preventDefault();
    const f = e.target;
    const r = await fetch('api.php?do=login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF': CSRF },
        body: JSON.stringify({ name: f.name.value, pass: f.pass.value }),
    });
    const j = await r.json();
    if (j.ok) { location.reload(); }
    else { document.getElementById('err').textContent = j.error || 'sign in failed'; }
    return false;
}
</script>

<?php else: ?>

<div class="grid">
    <section class="board" id="board">
        <!-- The stage shrinks to the plan image so slot percentages track the image
             itself, not the panel: the board then scales with the window. -->
        <div class="stage empty" id="stage">
            <img id="plan" alt="" hidden>
            <div class="noplan" id="noplan">
                <?= $admin ? 'No room plan yet — upload one below.' : 'No room plan yet.' ?>
            </div>
            <div id="slots"></div>
        </div>
    </section>

    <aside class="members">
        <h2>Members</h2>
        <ul id="members"></ul>
        <?php if ($admin): ?>
        <div class="admin">
            <h2>Admin</h2>
            <button onclick="addSlot()">Add slot</button>
            <form id="planform" onsubmit="return uploadPlan(event)">
                <input type="file" name="plan" accept="image/*,.svg" required>
                <button>Upload plan</button>
            </form>
            <p class="hint">Drag a slot to move it. Double-click to rename. Click to
               assign someone or see its addresses.</p>
        </div>
        <?php endif; ?>
        <p class="me">signed in as <b><?= h($user['name']) ?></b><?= $admin ? ' (admin)' : '' ?>
           — <a href="#" onclick="doLogout();return false">sign out</a></p>
    </aside>

    <section class="chat">
        <ul id="log"></ul>
        <form onsubmit="return say(event)">
            <input id="msg" placeholder="message" autocomplete="off" maxlength="1000">
            <button>Send</button>
        </form>
    </section>
</div>

<script>
const CSRF  = <?= json_encode($csrf) ?>;
const ME    = <?= json_encode($user['name']) ?>;
const ADMIN = <?= $admin ? 'true' : 'false' ?>;
</script>
<script src="assets/app.js"></script>

<?php endif; ?>
</body>
</html>
