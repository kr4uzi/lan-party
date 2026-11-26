<?php
// windrv API client (https://github.com/kr4uzi/windrv, api.php) used by menu.php and startnet.php

/**
 * Calls the windrv API and returns [response, error]: the decoded JSON response on success,
 * otherwise null and an error message.
 */
function windrvApi(array $config, array $query): array
{
    $url = $config["windrv"]["api"] . "?" . http_build_query($query);
    $context = stream_context_create(["http" => ["timeout" => 10, "ignore_errors" => true]]);
    $body = @file_get_contents($url, false, $context);
    if ($body === false) {
        return [null, "windrv API not reachable: {$url}"];
    }

    $response = json_decode($body, true);
    if (!is_array($response)) {
        return [null, "invalid windrv API response from {$url}"];
    }
    if (isset($response["error"])) {
        return [null, "windrv: " . $response["error"]];
    }
    return [$response, null];
}
