<?php
/**
 * Plugin Name: VHS-Kurse Importer Extended
 * Description: Importiert und synchronisiert Kursdaten aus einer JSON-Datei. Erstellt und aktualisiert automatisch Kurse, setzt Beitragsbilder (mit sicherem Download), deaktiviert nicht mehr vorhandene Kurse und zeigt automatisch einen „Jetzt anmelden“-Button im Widget an.
 * Version: 1.5
 * Author: Tim Heimes / Cognifaktur
 */

if (!defined('ABSPATH')) exit;

define('VHS_POST_TYPE', 'vhs_kurs');

// --- CPT registrieren ---
add_action('init', function() {
    register_post_type(VHS_POST_TYPE, [
        'labels' => [
            'name' => 'Kurse',
            'singular_name' => 'Kurs',
            'add_new_item' => 'Neuen Kurs hinzufügen',
            'edit_item' => 'Kurs bearbeiten',
        ],
        'public' => true,
        'has_archive' => true,
        'menu_icon' => 'dashicons-welcome-learn-more',
        'supports' => ['title', 'editor', 'thumbnail', 'custom-fields'],
        'show_in_rest' => true,
    ]);
});

// --- JSON Upload erlauben ---
add_filter('upload_mimes', fn($m) => array_merge($m, ['json' => 'application/json', 'svg' => 'image/svg+xml', 'webp' => 'image/webp']));

// --- Admin-Menü ---
add_action('admin_menu', function() {
    add_menu_page('VHS-Kurse', 'VHS-Kurse', 'manage_options', 'vhs-kurse', 'vhs_kurse_admin_page', 'dashicons-update');
    add_submenu_page('vhs-kurse', '⚙️ Custom Fields', '⚙️ Custom Fields', 'manage_options', 'vhs-custom-fields', 'vhs_custom_fields_page');
});

// --- Admin-Seite: Import ---
function vhs_kurse_admin_page() {
    $messages = [];
    $current_source = get_option('vhs_source_choice', 'url');
    if (!in_array($current_source, ['url', 'upload'], true)) {
        $current_source = 'url';
    }

    if (isset($_POST['save_json_url'])) {
        $saved_url_value = esc_url_raw($_POST['vhs_json_url']);
        update_option('vhs_json_url', $saved_url_value);
        update_option('vhs_source_choice', 'url');
        $current_source = 'url';
        $messages[] = ['class' => 'updated', 'text' => '✅ JSON-Quelle gespeichert.'];
    }

    if (!empty($_FILES['vhs_json_upload']['tmp_name']) && isset($_POST['upload_json'])) {
        $upload = wp_handle_upload($_FILES['vhs_json_upload'], ['test_form' => false]);
        if (!isset($upload['error'])) {
            update_option('vhs_uploaded_json', $upload['file']);
            update_option('vhs_source_choice', 'upload');
            $current_source = 'upload';
            $messages[] = ['class' => 'updated', 'text' => '✅ Datei hochgeladen: <code>' . esc_html(basename($upload['file'])) . '</code>.'];
        } else {
            $messages[] = ['class' => 'error', 'text' => 'Fehler: ' . esc_html($upload['error'])];
        }
    }

    $saved_url_value = get_option('vhs_json_url', '');
    $uploaded_path = get_option('vhs_uploaded_json', '');
    $uploaded_exists = $uploaded_path && file_exists($uploaded_path);
    $uploaded_file_name = $uploaded_path ? basename($uploaded_path) : '';

    if (isset($_POST['vhs_import_now'])) {
        $selected_source = sanitize_text_field($_POST['vhs_source_choice'] ?? $current_source);
        if (!in_array($selected_source, ['url', 'upload'], true)) {
            $selected_source = $current_source;
        }
        update_option('vhs_source_choice', $selected_source);
        $current_source = $selected_source;

        if ($selected_source === 'upload') {
            if (!$uploaded_exists) {
                $messages[] = ['class' => 'error', 'text' => '❌ Keine gültige hochgeladene Datei gefunden. Bitte laden Sie eine neue Datei hoch.'];
            } else {
                $result = vhs_import_kurse($uploaded_path);
                $messages[] = vhs_build_import_message($result, 'Hochgeladene Datei <code>' . esc_html($uploaded_file_name) . '</code>');
            }
        } else {
            if (empty($saved_url_value)) {
                $messages[] = ['class' => 'error', 'text' => '❌ Keine JSON-URL gespeichert. Bitte tragen Sie eine URL ein.'];
            } else {
                $result = vhs_import_kurse($saved_url_value);
                $messages[] = vhs_build_import_message($result, 'Gespeicherte URL');
            }
        }
    }

    if ($current_source === 'upload' && !$uploaded_exists && $uploaded_path) {
        $messages[] = ['class' => 'notice notice-warning', 'text' => '⚠️ Die ausgewählte Datei konnte nicht gefunden werden. Bitte erneut hochladen.'];
    }

    if ($current_source === 'url' && empty($saved_url_value)) {
        $messages[] = ['class' => 'notice notice-warning', 'text' => '⚠️ Es ist keine JSON-URL gespeichert. Bitte ergänzen Sie eine URL, bevor Sie importieren.'];
    }

    $saved_url_attr = esc_attr($saved_url_value);
    $saved_url_display = $saved_url_value ? '<code>' . esc_html($saved_url_value) . '</code>' : '<em>Keine URL gespeichert</em>';
    $uploaded_file_display = $uploaded_exists ? '<code>' . esc_html($uploaded_file_name) . '</code>' : '<em>Keine Datei verfügbar</em>';
    if ($uploaded_path && !$uploaded_exists) {
        $uploaded_file_display .= ' <span class="description">(Datei nicht gefunden)</span>';
    }

    if ($current_source === 'upload' && $uploaded_exists) {
        $active_source_html = 'Hochgeladene Datei <code>' . esc_html($uploaded_file_name) . '</code>';
    } elseif ($current_source === 'upload') {
        $active_source_html = 'Hochgeladene Datei <em>nicht verfügbar</em>';
    } elseif (!empty($saved_url_value)) {
        $active_source_html = 'Gespeicherte URL <code>' . esc_html($saved_url_value) . '</code>';
    } else {
        $active_source_html = 'Gespeicherte URL <em>nicht gesetzt</em>';
    }

    foreach ($messages as $message) {
        $class = isset($message['class']) ? $message['class'] : 'updated';
        echo '<div class="' . esc_attr($class) . '"><p>' . wp_kses_post($message['text']) . '</p></div>';
    }

    $last_result = get_option('vhs_last_import_result');
    if (is_array($last_result) && !empty($last_result['status'])) {
        echo '<div class="notice notice-info"><p>' . wp_kses_post(vhs_render_last_result($last_result)) . '</p></div>';
    }

    echo '<div class="notice notice-info"><p>Aktive Quelle für den nächsten Import: <strong>' . $active_source_html . '</strong></p></div>';

    echo '<div class="wrap"><h1>VHS-Kurse Import</h1>';
    echo '<form method="post" enctype="multipart/form-data">';

    echo '<h2>1️⃣ JSON-URL</h2>';
    echo '<p><input type="url" name="vhs_json_url" value="' . $saved_url_attr . '" size="60"> ';
    submit_button('Speichern', 'secondary', 'save_json_url', false);
    echo '</p>';
    echo '<p class="description">Gespeicherte URL: ' . $saved_url_display . '</p>';

    echo '<h2>2️⃣ Lokale Datei hochladen</h2>';
    echo '<input type="file" name="vhs_json_upload" accept=".json"> ';
    submit_button('Datei hochladen', 'secondary', 'upload_json', false);
    echo '<p class="description">Aktuelle Datei: ' . $uploaded_file_display . '</p>';

    echo '<h2>3️⃣ Quelle für den Import wählen</h2>';
    echo '<fieldset style="margin-bottom:1rem;">';
    echo '<label style="display:block;margin-bottom:0.6rem;"><input type="radio" name="vhs_source_choice" value="url" ' . checked($current_source, 'url', false) . '> Gespeicherte URL ' . $saved_url_display . '</label>';
    echo '<label style="display:block;"><input type="radio" name="vhs_source_choice" value="upload" ' . checked($current_source, 'upload', false) . '> Hochgeladene Datei ' . $uploaded_file_display . '</label>';
    echo '</fieldset>';

    echo '<h2>4️⃣ Import starten</h2>';
    submit_button('Jetzt importieren', 'primary', 'vhs_import_now');
    echo '</form></div>';
}


// --- Cronjob täglich ---
if (!wp_next_scheduled('vhs_import_cron')) {
    wp_schedule_event(time(), 'daily', 'vhs_import_cron');
}
add_action('vhs_import_cron', function() {
    vhs_import_kurse();
});

// --- Hilfsfunktionen für JSON-Verarbeitung ---
function vhs_normalize_json_url($url) {
    $parts = wp_parse_url($url);
    if (!$parts || empty($parts['host'])) {
        return $url;
    }

    if ($parts['host'] === 'github.com' && !empty($parts['path'])) {
        $path_segments = array_values(array_filter(explode('/', $parts['path'])));
        $blob_index = array_search('blob', $path_segments, true);
        if ($blob_index !== false && isset($path_segments[$blob_index + 2])) {
            $owner = $path_segments[0] ?? null;
            $repo = $path_segments[1] ?? null;
            $branch = $path_segments[$blob_index + 1] ?? null;
            $file_path_segments = array_slice($path_segments, $blob_index + 2);
            if ($owner && $repo && $branch && $file_path_segments) {
                $normalized = sprintf(
                    'https://raw.githubusercontent.com/%s/%s/%s/%s',
                    $owner,
                    $repo,
                    $branch,
                    implode('/', $file_path_segments)
                );

                if (!empty($parts['query'])) {
                    $normalized = $normalized . '?' . $parts['query'];
                }

                return $normalized;
            }
        }
    }

    return $url;
}

function vhs_load_json_data($json_source) {
    if (filter_var($json_source, FILTER_VALIDATE_URL)) {
        $normalized_url = vhs_normalize_json_url($json_source);
        $request_url = add_query_arg('_vhs_cache_bust', time(), $normalized_url);
        $response = wp_remote_get($request_url, [
            'timeout' => 20,
            'redirection' => 5,
            'headers' => [
                'Cache-Control' => 'no-cache, no-store, must-revalidate',
                'Pragma' => 'no-cache',
            ],
        ]);
        if (is_wp_error($response)) {
            return $response;
        }
        $code = wp_remote_retrieve_response_code($response);
        if ($code !== 200) {
            return new WP_Error('vhs_http_error', 'HTTP ' . $code . ' beim Abruf der JSON-Quelle.');
        }
        $body = wp_remote_retrieve_body($response);
    } else {
        if (!is_readable($json_source)) {
            return new WP_Error('vhs_file_error', 'Die ausgewählte Datei kann nicht gelesen werden.');
        }
        $body = file_get_contents($json_source);
    }

    $data = json_decode($body, true);
    if (!is_array($data)) {
        return new WP_Error('vhs_invalid_json', 'Die JSON-Daten konnten nicht verarbeitet werden.');
    }

    return $data;
}

function vhs_extract_courses_array($data) {
    if (empty($data)) {
        return [];
    }

    if (isset($data[0]) && is_array($data[0])) {
        return $data;
    }

    $candidate_keys = [
        'kurse', 'Kurse',
        'courses', 'Courses',
        'veranstaltungen', 'Veranstaltungen',
        'data', 'results'
    ];

    foreach ($candidate_keys as $key) {
        if (isset($data[$key]) && is_array($data[$key])) {
            if (isset($data[$key][0]) && is_array($data[$key][0])) {
                return $data[$key];
            }
            if (is_array($data[$key])) {
                $inner = vhs_extract_courses_array($data[$key]);
                if (!is_wp_error($inner)) {
                    return $inner;
                }
            }
        }
    }

    $guessed = [];
    foreach ($data as $value) {
        if (is_array($value) && (
                isset($value['guid']) ||
                isset($value['uuid']) ||
                isset($value['uid']) ||
                isset($value['id']) ||
                isset($value['nummer']) ||
                isset($value['kursnummer'])
            )
        ) {
            $guessed[] = $value;
        }
    }

    if (!empty($guessed)) {
        return $guessed;
    }

    return new WP_Error('vhs_invalid_json_structure', 'Die JSON-Struktur konnte nicht als Kursliste erkannt werden.');
}

function vhs_get_first_value(array $source, array $keys) {
    foreach ($keys as $key) {
        if (isset($source[$key]) && $source[$key] !== '' && $source[$key] !== null) {
            return $source[$key];
        }
    }
    return '';
}

// --- Hauptimporter mit sicherem Bild-Download ---
function vhs_import_kurse($json_source = null) {
    if (!$json_source) {
        $json_source = get_option('vhs_json_url');
    }
    if (!$json_source) {
        return new WP_Error('vhs_missing_source', 'Keine Datenquelle konfiguriert.');
    }

    $data = vhs_load_json_data($json_source);
    if (is_wp_error($data)) {
        vhs_store_import_result([
            'status'  => 'error',
            'message' => $data->get_error_message(),
            'source'  => $json_source,
        ]);
        return $data;
    }

    $courses = vhs_extract_courses_array($data);
    if (is_wp_error($courses)) {
        vhs_store_import_result([
            'status'  => 'error',
            'message' => $courses->get_error_message(),
            'source'  => $json_source,
        ]);
        return $courses;
    }

    $found_guids = [];
    $created = 0;
    $updated = 0;
    $total = 0;

    $now_local = current_time('mysql');
    $now_gmt = current_time('mysql', true);

    foreach ($courses as $kurs) {
        if (!is_array($kurs)) {
            continue;
        }

        $guid = sanitize_text_field(
            vhs_get_first_value($kurs, ['guid', 'uuid', 'uid', 'id', 'nummer', 'kursnummer'])
        );

        if (!$guid) {
            continue;
        }

        $found_guids[] = $guid;
        $total++;

        $title_raw = vhs_get_first_value($kurs, ['titel', 'title', 'name', 'kurs', 'veranstaltung']);
        $content_raw = vhs_get_first_value($kurs, ['beschreibung_lang', 'beschreibung', 'description', 'beschreibung_kurz', 'text']);
        $link_raw = vhs_get_first_value($kurs, ['link', 'anmeldelink', 'anmeldung_link', 'anmeldung_url', 'url', 'online_anmeldung']);
        $dozent_raw = vhs_get_first_value($kurs, ['dozent', 'leitung', 'kursleitung', 'dozent_name', 'leiter']);
        $preis_raw = vhs_get_first_value($kurs, ['preis', 'gebuehr', 'gebühr', 'fee', 'kosten']);
        $nummer_raw = vhs_get_first_value($kurs, ['nummer', 'kursnummer', 'id', 'code']);
        $ort_raw = vhs_get_first_value($kurs, ['ort', 'standort', 'location', 'raum']);
        $zeiten_raw = vhs_get_first_value($kurs, ['zeiten', 'zeit', 'termine', 'zeitraum', 'dauer']);
        $bild_raw = vhs_get_first_value($kurs, ['bild', 'bild_url', 'image', 'image_url', 'thumbnail']);

        $post_title = sanitize_text_field($title_raw ?: 'Ohne Titel');
        $post_content = $content_raw ? wp_kses_post($content_raw) : '';

        $existing = get_posts([
            'post_type'  => VHS_POST_TYPE,
            'meta_key'   => 'vhs_guid',
            'meta_value' => $guid,
            'numberposts'=> 1
        ]);

        $post_data = [
            'post_title'        => $post_title,
            'post_content'      => $post_content,
            'post_type'         => VHS_POST_TYPE,
            'post_status'       => 'publish',
            'post_date'         => $now_local,
            'post_date_gmt'     => $now_gmt,
            'post_modified'     => $now_local,
            'post_modified_gmt' => $now_gmt,
        ];

        if ($existing) {
            $post_id = $existing[0]->ID;
            $post_data['ID'] = $post_id;
            $post_data['edit_date'] = true;
            wp_update_post($post_data);
            $updated++;
        } else {
            $post_id = wp_insert_post($post_data);
            $created++;
        }

        update_post_meta($post_id, 'vhs_guid', $guid);
        update_post_meta($post_id, 'vhs_link', esc_url_raw($link_raw));
        update_post_meta($post_id, 'vhs_dozent', sanitize_text_field($dozent_raw));
        update_post_meta($post_id, 'vhs_preis', sanitize_text_field($preis_raw));
        update_post_meta($post_id, 'vhs_nummer', sanitize_text_field($nummer_raw));
        update_post_meta($post_id, 'vhs_ort', sanitize_text_field($ort_raw));
        update_post_meta($post_id, 'vhs_zeiten', sanitize_text_field($zeiten_raw));
        update_post_meta($post_id, 'vhs_bild', esc_url_raw($bild_raw));

        if (!empty($bild_raw)) {
            $image_url = esc_url_raw($bild_raw);
            $image_name = basename(parse_url($image_url, PHP_URL_PATH));
            $upload_dir = wp_upload_dir();

            $response = wp_remote_get($image_url, ['timeout' => 20]);
            if (!is_wp_error($response) && wp_remote_retrieve_response_code($response) === 200) {
                $image_data = wp_remote_retrieve_body($response);
                $file_path = $upload_dir['path'] . '/' . $image_name;
                file_put_contents($file_path, $image_data);

                $file_type = wp_check_filetype($image_name, null);
                $attachment = [
                    'post_mime_type' => $file_type['type'],
                    'post_title'     => sanitize_file_name(pathinfo($image_name, PATHINFO_FILENAME)),
                    'post_content'   => '',
                    'post_status'    => 'inherit'
                ];
                $attach_id = wp_insert_attachment($attachment, $file_path, $post_id);
                require_once ABSPATH . 'wp-admin/includes/image.php';
                $attach_data = wp_generate_attachment_metadata($attach_id, $file_path);
                wp_update_attachment_metadata($attach_id, $attach_data);
                set_post_thumbnail($post_id, $attach_id);
            } else {
                error_log('⚠️ Fehler beim Bild-Download: ' . $image_url);
            }
        }
    }

    $all_existing = get_posts(['post_type' => VHS_POST_TYPE, 'numberposts' => -1]);
    $deactivated = 0;
    foreach ($all_existing as $p) {
        $guid = get_post_meta($p->ID, 'vhs_guid', true);
        if ($guid && !in_array($guid, $found_guids, true)) {
            if ($p->post_status !== 'draft') {
                wp_update_post(['ID' => $p->ID, 'post_status' => 'draft']);
                $deactivated++;
            }
        }
    }

    $result = [
        'status'       => 'success',
        'total'        => $total,
        'created'      => $created,
        'updated'      => $updated,
        'deactivated'  => $deactivated,
        'source'       => $json_source,
        'timestamp'    => current_time('timestamp'),
    ];

    vhs_store_import_result($result);

    return $result;
}

function vhs_store_import_result($result) {
    $result['timestamp'] = $result['timestamp'] ?? current_time('timestamp');
    update_option('vhs_last_import_result', $result);
}

function vhs_build_import_message($result, $source_label) {
    if (is_wp_error($result)) {
        return [
            'class' => 'error',
            'text'  => '❌ Import fehlgeschlagen (' . esc_html($source_label) . '): ' . esc_html($result->get_error_message()),
        ];
    }

    $text = sprintf(
        '✅ Import abgeschlossen (%s). %d Gesamt, %d erstellt, %d aktualisiert, %d deaktiviert.',
        wp_kses_post($source_label),
        intval($result['total'] ?? 0),
        intval($result['created'] ?? 0),
        intval($result['updated'] ?? 0),
        intval($result['deactivated'] ?? 0)
    );

    return [
        'class' => 'updated',
        'text'  => $text,
    ];
}

function vhs_render_last_result($result) {
    $time = !empty($result['timestamp']) ? date_i18n('d.m.Y H:i', $result['timestamp']) : '';
    $source = !empty($result['source']) ? esc_html($result['source']) : 'Unbekannt';

    if (($result['status'] ?? '') === 'success') {
        return sprintf(
            'Letzter erfolgreicher Import am %s von <code>%s</code>: %d Gesamt, %d erstellt, %d aktualisiert, %d deaktiviert.',
            esc_html($time),
            $source,
            intval($result['total'] ?? 0),
            intval($result['created'] ?? 0),
            intval($result['updated'] ?? 0),
            intval($result['deactivated'] ?? 0)
        );
    }

    return sprintf(
        'Letzter Import-Versuch am %s von <code>%s</code> fehlgeschlagen: %s',
        esc_html($time),
        $source,
        esc_html($result['message'] ?? 'Unbekannter Fehler')
    );
}

// --- Shortcode für Felder ---
function vhs_parse_times_value($value) {
    $value = trim((string) $value);
    if ($value === '') {
        return [[], '', []];
    }

    $lines = preg_split("/\n+/", $value);
    $lines = array_values(array_filter(array_map('trim', $lines), function($line) {
        return $line !== '';
    }));

    $summary = [];
    $heading = '';
    $details = [];
    $in_details = false;

    foreach ($lines as $line) {
        if (!$in_details && preg_match('/^termine/i', $line)) {
            $heading = $line;
            $in_details = true;
            continue;
        }

        if ($in_details) {
            $details[] = ltrim(preg_replace('/^-\s*/', '', $line));
        } else {
            $summary[] = $line;
        }
    }

    return [$summary, $heading, $details];
}

function vhs_format_times_html($value) {
    [$summary, $heading, $details] = vhs_parse_times_value($value);

    if (empty($summary) && empty($details)) {
        return '';
    }

    $html = '<div class="vhs-times">';

    if (!empty($summary)) {
        $html .= '<ul class="vhs-times-summary">';
        foreach ($summary as $line) {
            $html .= '<li>' . esc_html($line) . '</li>';
        }
        $html .= '</ul>';
    }

    if (!empty($heading)) {
        $html .= '<div class="vhs-times-heading">' . esc_html($heading) . '</div>';
    }

    if (!empty($details)) {
        $html .= '<ul class="vhs-times-details">';
        foreach ($details as $line) {
            if ($line === '') {
                continue;
            }
            $html .= '<li>' . esc_html($line) . '</li>';
        }
        $html .= '</ul>';
    }

    $html .= '</div>';

    return $html;
}

function vhs_render_field_markup($key, $label, $value) {
    $has_label = $label !== null && $label !== '';

    if ($key === 'vhs_zeiten') {
        $formatted = vhs_format_times_html($value);
        if ($formatted === '') {
            return '';
        }

        $label_html = $has_label ? '<strong>' . esc_html($label) . ':</strong>' : '';

        return '<div class="vhs-field vhs-field-times">' . $label_html . '<div class="vhs-times-content">' . $formatted . '</div></div>';
    }

    if ($has_label) {
        return '<p class="vhs-field"><strong>' . esc_html($label) . ':</strong> ' . esc_html($value) . '</p>';
    }

    return '<p class="vhs-field">' . esc_html($value) . '</p>';
}

add_shortcode('vhs_field', function($atts) {
    $atts = shortcode_atts(['key' => '', 'label' => ''], $atts);
    if (empty($atts['key'])) return '';
    global $post;
    if (!$post) return '';
    $value = get_post_meta($post->ID, $atts['key'], true);
    if (!$value) return '';

    return vhs_render_field_markup($atts['key'], $atts['label'], $value);
});

// --- Automatisches CSS laden ---
add_action('wp_enqueue_scripts', function() {
    wp_register_style('vhs-kurse-style', false);
    wp_enqueue_style('vhs-kurse-style');
    wp_add_inline_style('vhs-kurse-style', "
.vhs-field-box{background:var(--ct-background-light,#f8f9fa);border:1px solid rgba(0,0,0,0.07);border-radius:12px;padding:1.2rem 1.5rem;margin:1.5rem 0;box-shadow:0 1px 4px rgba(0,0,0,0.04);}
.vhs-field-box h3{font-size:1.1rem;margin-bottom:0.8rem;border-bottom:1px solid rgba(0,0,0,0.05);padding-bottom:0.4rem;}
.vhs-field{margin:0.3rem 0;font-size:0.95rem;line-height:1.5;}
.vhs-field strong{min-width:6.5rem;display:inline-block;font-weight:600;color:var(--ct-primary,#333);}
.vhs-field-times{margin:0.9rem 0 0.8rem;}
.vhs-field-times strong{display:block;margin-bottom:0.4rem;min-width:auto;}
.vhs-times-content{display:flex;flex-direction:column;gap:0.45rem;}
.vhs-times-summary{display:flex;flex-wrap:wrap;gap:0.35rem;padding:0;margin:0;list-style:none;font-size:0.9rem;}
.vhs-times-summary li{background:rgba(0,0,0,0.05);border-radius:999px;padding:0.25rem 0.7rem;}
.vhs-times-heading{font-weight:600;color:var(--ct-primary,#333);font-size:0.92rem;}
.vhs-times-details{margin:0.2rem 0 0;padding-left:1.15rem;}
.vhs-times-details li{margin:0.2rem 0;}
.vhs-button{display:inline-block;margin-top:1rem;background:var(--ct-primary,#0073aa);color:#fff;padding:0.6rem 1.2rem;border-radius:8px;text-decoration:none;font-weight:600;transition:all 0.2s ease-in-out;}
.vhs-button:hover{background:var(--ct-primary-hover,#005b85);transform:translateY(-1px);}
");
});

// --- Automatischer Widget-Block ---
add_shortcode('vhs_widget', function() {
    global $post;
    if (!$post) return '';
    $fields = [
        'vhs_zeiten' => '🕓 Zeiten',
        'vhs_dozent' => '👤 Leitung',
        'vhs_nummer' => '🔢 Nummer',
        'vhs_ort'    => '📍 Ort',
        'vhs_preis'  => '💰 Preis'
    ];
    $html = '<div class="vhs-field-box"><h3>Kurs-Information</h3>';
    foreach ($fields as $key => $label) {
        $val = get_post_meta($post->ID, $key, true);
        if (!$val) continue;
        $field_markup = vhs_render_field_markup($key, $label, $val);
        if ($field_markup) {
            $html .= $field_markup;
        }
    }
    $link = get_post_meta($post->ID, 'vhs_link', true);
    if ($link) {
        $html .= '<a href="' . esc_url($link) . '" class="vhs-button" target=\"_blank\" rel=\"noopener\">Jetzt anmelden</a>';
    }
    $html .= '</div>';
    return $html;
});

// --- Feldübersicht im Admin ---
function vhs_custom_fields_page() {
    echo '<div class="wrap"><h1>⚙️ VHS-Kurse – Custom Fields</h1><table class="widefat"><thead><tr><th>Feldname</th><th>Beschreibung</th></tr></thead><tbody>';
    $fields = [
        'vhs_guid' => 'Eindeutige Kurs-ID',
        'vhs_link' => 'Anmeldelink',
        'vhs_dozent' => 'Leitung / Dozent',
        'vhs_preis' => 'Preis',
        'vhs_nummer' => 'Kursnummer',
        'vhs_ort' => 'Ort',
        'vhs_zeiten' => 'Zeiten',
        'vhs_bild' => 'Kursbild (URL)'
    ];
    foreach ($fields as $key => $label) {
        echo "<tr><td><code>$key</code></td><td>$label</td></tr>";
    }
    echo '</tbody></table></div>';
}
