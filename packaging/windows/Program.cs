using System.Diagnostics;
using Microsoft.Web.WebView2.WinForms;

namespace WaterRegimeGis;

internal static class Program
{
    private static readonly Uri AppUri = new("http://127.0.0.1:8765");
    private static Process? backendProcess;

    [STAThread]
    private static async Task Main()
    {
        ApplicationConfiguration.Initialize();
        using var form = new MainForm();
        form.Show();

        try
        {
            var releaseDir = AppContext.BaseDirectory;
            await Task.Run(() => EnsureLocalBackend(releaseDir));
            form.Navigate(AppUri);
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "Water Regime GIS", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            form.ShowMessage("Не удалось запустить приложение.\n\n" + ex.Message);
        }

        Application.Run(form);
        if (backendProcess is { HasExited: false })
        {
            backendProcess.Kill(entireProcessTree: true);
        }
    }

    private static void EnsureLocalBackend(string releaseDir)
    {
        if (BackendResponds()) return;

        var python = QgisPython();
        var script = Path.Combine(releaseDir, "scripts", "run_app.py");
        if (!File.Exists(script))
        {
            throw new InvalidOperationException("В release-пакете не найден scripts\\run_app.py. Скачайте полный архив Water Regime GIS из GitHub Release.");
        }

        backendProcess = StartBackend(python, script, releaseDir);
        WaitForBackend();
    }

    private static void WaitForBackend()
    {
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
        var deadline = DateTime.UtcNow.AddSeconds(90);
        while (DateTime.UtcNow < deadline)
        {
            try
            {
                using var response = client.GetAsync(AppUri).GetAwaiter().GetResult();
                if ((int)response.StatusCode is >= 200 and < 500) return;
            }
            catch
            {
                Thread.Sleep(1000);
            }
            if (backendProcess is { HasExited: true })
            {
                throw new InvalidOperationException("Локальный сервис завершился сразу после запуска. Проверьте установку QGIS.");
            }
        }
        throw new InvalidOperationException("Локальный сервис не ответил за 90 секунд.");
    }

    private static bool BackendResponds()
    {
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
            using var response = client.GetAsync(AppUri).GetAwaiter().GetResult();
            return (int)response.StatusCode is >= 200 and < 500;
        }
        catch
        {
            return false;
        }
    }

    private static string QgisPython()
    {
        var candidates = new List<string>();
        var configured = Environment.GetEnvironmentVariable("WATER_REGIME_GIS_QGIS_PYTHON");
        if (!string.IsNullOrWhiteSpace(configured)) candidates.Add(configured);
        candidates.AddRange(FindFiles(@"C:\Program Files", "python-qgis.bat").OrderByDescending(path => path));
        candidates.AddRange(FindFiles(@"C:\OSGeo4W", "python-qgis.bat").OrderByDescending(path => path));
        foreach (var candidate in candidates)
        {
            if (File.Exists(candidate)) return candidate;
        }
        throw new InvalidOperationException("QGIS не найден. Установите чистый QGIS с официального сайта или OSGeo4W и откройте приложение снова.");
    }

    private static IEnumerable<string> FindFiles(string root, string pattern)
    {
        if (!Directory.Exists(root)) return [];
        try
        {
            return Directory.EnumerateFiles(root, pattern, SearchOption.AllDirectories).ToList();
        }
        catch
        {
            return [];
        }
    }

    private static Process StartBackend(string python, string script, string cwd)
    {
        var isBatch = python.EndsWith(".bat", StringComparison.OrdinalIgnoreCase) || python.EndsWith(".cmd", StringComparison.OrdinalIgnoreCase);
        var process = new Process
        {
            StartInfo = new ProcessStartInfo(isBatch ? "cmd.exe" : python, isBatch ? $"/c \"\"{python}\" \"{script}\"\"" : $"\"{script}\"")
            {
                WorkingDirectory = cwd,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            }
        };
        process.StartInfo.Environment["WATER_REGIME_GIS_NO_BROWSER"] = "1";
        process.StartInfo.Environment["WATER_REGIME_GIS_PORT"] = "8765";
        process.StartInfo.Environment["WATER_REGIME_GIS_RUNTIME"] = "local-release";
        process.Start();
        return process;
    }
}

internal sealed class MainForm : Form
{
    private readonly WebView2 webView = new() { Dock = DockStyle.Fill };
    private readonly Label status = new()
    {
        Dock = DockStyle.Fill,
        TextAlign = ContentAlignment.MiddleCenter,
        Font = new Font("Segoe UI", 14),
        Text = "Запуск Water Regime GIS...",
    };

    public MainForm()
    {
        Text = "Water Regime GIS";
        Width = 1280;
        Height = 860;
        Controls.Add(status);
    }

    public void Navigate(Uri uri)
    {
        Controls.Clear();
        Controls.Add(webView);
        webView.Source = uri;
    }

    public void ShowMessage(string message)
    {
        status.Text = message;
    }
}
