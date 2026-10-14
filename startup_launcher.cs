// Lightweight Windows-only launcher for the OCR program.
// Uses WPF MediaElement, which relies on Windows' native media playback stack.

using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace OcrLauncher
{
    public sealed class StartupWindow : Window
    {
        private const string MainProgramName = "ocr_qt.exe";
        private const string ReadyEventEnvironmentName = "OCR_LAUNCH_READY_EVENT";

        private readonly string _applicationDirectory;
        private readonly string[] _arguments;
        private readonly bool _previewMode;
        private readonly DispatcherTimer _pollTimer;
        private EventWaitHandle _readyEvent;
        private Process _mainProcess;
        private MediaElement _video;
        private Grid _mediaCanvas;
        private Image _loadingImage;

        public StartupWindow(string applicationDirectory, string[] arguments)
        {
            _applicationDirectory = applicationDirectory;
            _arguments = arguments;
            _previewMode = HasPreviewArgument(arguments);

            Title = "正在打开软件";
            Width = 760;
            Height = 480;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            WindowStyle = WindowStyle.None;
            ResizeMode = ResizeMode.NoResize;
            ShowInTaskbar = false;
            Topmost = true;
            Background = Brushes.White;

            Content = BuildContent();
            // If no loading image was supplied, keep the launcher invisible
            // until the first video frame can be displayed.  When loading.png
            // exists it is shown immediately instead of a black video surface.
            if (_video != null && _loadingImage == null)
            {
                Opacity = 0;
            }
            _pollTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(50) };
            _pollTimer.Tick += PollMainProgram;
            if (_previewMode)
            {
                KeyDown += delegate(object sender, System.Windows.Input.KeyEventArgs eventArgs)
                {
                    if (eventArgs.Key == System.Windows.Input.Key.Escape)
                    {
                        Close();
                    }
                };
                MouseLeftButtonDown += delegate { Close(); };
            }
        }

        private static bool HasPreviewArgument(string[] arguments)
        {
            if (arguments == null)
            {
                return false;
            }
            foreach (string argument in arguments)
            {
                if (string.Equals(argument, "--preview", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            return false;
        }

        private UIElement BuildContent()
        {
            string videoPath = Path.Combine(_applicationDirectory, "opening.mp4");
            var canvas = new Grid { Background = Brushes.White };
            _mediaCanvas = canvas;
            if (File.Exists(videoPath))
            {
                _video = new MediaElement
                {
                    LoadedBehavior = MediaState.Manual,
                    UnloadedBehavior = MediaState.Stop,
                    Stretch = Stretch.Uniform,
                    Volume = 0,
                    Source = new Uri(videoPath, UriKind.Absolute),
                };
                // With LoadedBehavior.Manual, explicitly start playback once
                // the visual has joined the window. Waiting for MediaOpened
                // before calling Play can leave some WPF media pipelines idle.
                _video.Loaded += delegate
                {
                    _video.Play();
                };
                _video.MediaOpened += delegate
                {
                    MatchWindowToVideoAspect();
                    _video.Play();
                    RevealVideoOnNextRender();
                };
                _video.MediaEnded += delegate
                {
                    _video.Position = TimeSpan.Zero;
                    _video.Play();
                };
                _video.MediaFailed += delegate
                {
                    ShowVideoFallback();
                };
                canvas.Children.Add(_video);
                // Keep the image above the video while Windows prepares the
                // decoder. The video itself remains visible to WPF so frames
                // can actually be decoded and playback can advance.
                AddLoadingImage(canvas);
            }
            else
            {
                // Image-only mode: loading.png remains visible until the
                // main program signals that its main window is ready.
                if (!AddLoadingImage(canvas))
                {
                    AddFallbackContent(canvas);
                }
            }
            return canvas;
        }

        private bool AddLoadingImage(Grid canvas)
        {
            string loadingImagePath = Path.Combine(_applicationDirectory, "loading.png");
            if (!File.Exists(loadingImagePath))
            {
                return false;
            }

            try
            {
                var bitmap = new BitmapImage();
                bitmap.BeginInit();
                bitmap.CacheOption = BitmapCacheOption.OnLoad;
                bitmap.UriSource = new Uri(loadingImagePath, UriKind.Absolute);
                bitmap.EndInit();
                bitmap.Freeze();
                _loadingImage = new Image
                {
                    Source = bitmap,
                    Stretch = Stretch.UniformToFill,
                };
                canvas.Children.Add(_loadingImage);
                return true;
            }
            catch (Exception)
            {
                // Ignore an invalid optional loading image. The launcher will
                // use its invisible-until-video-ready behavior instead.
                _loadingImage = null;
                return false;
            }
        }

        private void MatchWindowToVideoAspect()
        {
            if (_video == null || _video.NaturalVideoWidth <= 0 || _video.NaturalVideoHeight <= 0)
            {
                return;
            }

            // Keep the launch window reasonably sized, while making its
            // aspect ratio identical to the source video.  Stretch.Uniform
            // can therefore show the entire frame without letterboxing.
            double aspectRatio = (double)_video.NaturalVideoWidth / _video.NaturalVideoHeight;
            Rect workArea = SystemParameters.WorkArea;
            double height = 480;
            double width = height * aspectRatio;
            double maximumWidth = Math.Max(320, workArea.Width * 0.90);
            double maximumHeight = Math.Max(240, workArea.Height * 0.80);

            if (width > maximumWidth)
            {
                width = maximumWidth;
                height = width / aspectRatio;
            }
            if (height > maximumHeight)
            {
                height = maximumHeight;
                width = height * aspectRatio;
            }

            Width = Math.Round(width);
            Height = Math.Round(height);
            // The window is still transparent at this point, so centering it
            // again does not create a visible resize or move animation.
            Left = workArea.Left + ((workArea.Width - Width) / 2);
            Top = workArea.Top + ((workArea.Height - Height) / 2);
        }

        private void RevealVideoOnNextRender()
        {
            // MediaOpened means Windows has accepted the source. Queue the
            // switch for the next render pass instead of adding a fixed delay;
            // this keeps loading.png on screen only as long as necessary.
            Dispatcher.BeginInvoke(new Action(RevealVideo), DispatcherPriority.Render);
        }

        private void RevealVideo()
        {
            if (_video == null)
            {
                return;
            }
            _video.Opacity = 1;
            if (_loadingImage != null)
            {
                _loadingImage.Visibility = Visibility.Collapsed;
            }
            Opacity = 1;
        }

        private void ShowVideoFallback()
        {
            if (_video != null)
            {
                _video.Stop();
                _mediaCanvas.Children.Remove(_video);
                _video = null;
            }
            if (_loadingImage != null)
            {
                // The loading picture is also the best fallback when Windows
                // cannot decode the selected video file.
                Opacity = 1;
                return;
            }
            _mediaCanvas.Background = Brushes.White;
            AddFallbackContent(_mediaCanvas);
            Opacity = 1;
        }
        private void AddFallbackContent(Grid canvas)
        {
            string imagePath = Path.Combine(_applicationDirectory, "opening.png");
            if (File.Exists(imagePath))
            {
                try
                {
                    var bitmap = new BitmapImage();
                    bitmap.BeginInit();
                    bitmap.CacheOption = BitmapCacheOption.OnLoad;
                    bitmap.UriSource = new Uri(imagePath, UriKind.Absolute);
                    bitmap.EndInit();
                    bitmap.Freeze();
                    canvas.Children.Add(new Image { Source = bitmap, Stretch = Stretch.Uniform });
                    return;
                }
                catch (Exception)
                {
                    // A text fallback is shown below when the PNG is invalid.
                }
            }

            canvas.Children.Add(new TextBlock
            {
                Text = "正在打开软件，请稍候…",
                FontFamily = new FontFamily("Microsoft YaHei UI"),
                FontSize = 18,
                Foreground = new SolidColorBrush(Color.FromRgb(32, 33, 36)),
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center,
            });
        }

        public void BeginLaunching()
        {
            if (_previewMode)
            {
                Activate();
                return;
            }
            string mainProgramPath = Path.Combine(_applicationDirectory, MainProgramName);
            if (!File.Exists(mainProgramPath))
            {
                MessageBox.Show("未找到主程序：\n" + mainProgramPath, "启动失败", MessageBoxButton.OK, MessageBoxImage.Error);
                Close();
                return;
            }

            string eventName = "Local\\OCRLauncherReady-" + Guid.NewGuid().ToString("N");
            try
            {
                _readyEvent = new EventWaitHandle(false, EventResetMode.ManualReset, eventName);
                var startInfo = new ProcessStartInfo(mainProgramPath, JoinArguments(_arguments))
                {
                    UseShellExecute = false,
                    WorkingDirectory = _applicationDirectory,
                };
                startInfo.EnvironmentVariables[ReadyEventEnvironmentName] = eventName;
                _mainProcess = Process.Start(startInfo);
                _pollTimer.Start();
            }
            catch (Exception exception)
            {
                MessageBox.Show("无法启动主程序：\n" + exception.Message, "启动失败", MessageBoxButton.OK, MessageBoxImage.Error);
                Close();
            }
        }
        private static string JoinArguments(string[] arguments)
        {
            if (arguments == null || arguments.Length == 0)
            {
                return string.Empty;
            }
            var quotedArguments = new string[arguments.Length];
            for (int index = 0; index < arguments.Length; index++)
            {
                quotedArguments[index] = '"' + arguments[index].Replace("\\", "\\\\").Replace("\"", "\\\"") + '"';
            }
            return string.Join(" ", quotedArguments);
        }

        private void PollMainProgram(object sender, EventArgs eventArgs)
        {
            if (_readyEvent != null && _readyEvent.WaitOne(0))
            {
                Close();
                return;
            }
            if (_mainProcess != null && _mainProcess.HasExited)
            {
                MessageBox.Show("主程序在完成初始化前退出。", "启动失败", MessageBoxButton.OK, MessageBoxImage.Error);
                Close();
            }
        }

        protected override void OnClosed(EventArgs eventArgs)
        {
            _pollTimer.Stop();

            if (_video != null)
            {
                _video.Stop();
            }
            if (_readyEvent != null)
            {
                _readyEvent.Close();
            }
            base.OnClosed(eventArgs);
            Application.Current.Shutdown();
        }
    }

    public sealed class StartupApplication : Application
    {
        [STAThread]
        public static int Main(string[] arguments)
        {
            var application = new StartupApplication();
            return application.Run();
        }

        protected override void OnStartup(StartupEventArgs eventArgs)
        {
            base.OnStartup(eventArgs);
            var window = new StartupWindow(AppDomain.CurrentDomain.BaseDirectory, eventArgs.Args);
            MainWindow = window;
            window.Show();
            window.Dispatcher.BeginInvoke(new Action(window.BeginLaunching), DispatcherPriority.ApplicationIdle);
        }
    }
}
