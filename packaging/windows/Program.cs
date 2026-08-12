using System.Diagnostics;
using Microsoft.Web.WebView2.WinForms;

namespace WaterRegimeGis;

internal static class Program
{
    private static readonly Uri AppUri = new("http://127.0.0.1:8765");

    [STAThread]
    private static async Task Main()
    {
        ApplicationConfiguration.Initialize();
        using var form = new MainForm();
        form.Show();

        try
        {
            var releaseDir = AppContext.BaseDirectory;
            await Task.Run(() => EnsureDockerBackend(releaseDir));
            form.Navigate(AppUri);
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "Water Regime GIS", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            form.ShowMessage("Не удалось запустить приложение.\n\n" + ex.Message);
        }

        Application.Run(form);
    }

    private static void EnsureDockerBackend(string releaseDir)
    {
        Run("docker", "info", releaseDir, "Docker Desktop не найден или не запущен. Установите/запустите Docker Desktop и откройте приложение снова.");
        if (RunStatus("docker", "image inspect water-regime-gis:release", releaseDir) != 0)
        {
            Run("docker", "load -i water-regime-gis-image.tar", releaseDir);
        }
        Run("docker", "compose up -d", releaseDir);
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
        }
        throw new InvalidOperationException("Локальный сервис не ответил за 90 секунд.");
    }

    private static int RunStatus(string file, string arguments, string cwd)
    {
        try
        {
            using var process = StartProcess(file, arguments, cwd);
            process.WaitForExit();
            return process.ExitCode;
        }
        catch
        {
            return 127;
        }
    }

    private static void Run(string file, string arguments, string cwd, string? friendlyError = null)
    {
        using var process = StartProcess(file, arguments, cwd);
        process.WaitForExit();
        if (process.ExitCode == 0) return;

        var output = process.StandardOutput.ReadToEnd() + process.StandardError.ReadToEnd();
        throw new InvalidOperationException(friendlyError ?? (string.IsNullOrWhiteSpace(output) ? $"{file} {arguments} failed." : output.Trim()));
    }

    private static Process StartProcess(string file, string arguments, string cwd)
    {
        var process = new Process
        {
            StartInfo = new ProcessStartInfo(file, arguments)
            {
                WorkingDirectory = cwd,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            }
        };
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
