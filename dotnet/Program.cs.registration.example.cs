// dotnet/Program.cs.registration.example.cs
// Add this registration to the existing .NET Program.cs.
// Keep the Coordinator URL in configuration, not hard-coded in source.
builder.Services.AddHttpClient<YourApp.Assistant.AssistantCoordinatorClient>(client =>
{
    var baseUrl = builder.Configuration["AssistantCoordinator:BaseUrl"]
        ?? throw new InvalidOperationException("AssistantCoordinator:BaseUrl is not configured.");

    client.BaseAddress = new Uri(baseUrl);
    client.Timeout = TimeSpan.FromSeconds(60);
});

// Example appsettings.Development.json entry:
// "AssistantCoordinator": { "BaseUrl": "http://localhost:8001" }
//
// If .NET runs in the same Docker network, use:
// "AssistantCoordinator": { "BaseUrl": "http://coordinator:8001" }
