// dotnet/AssistantCoordinatorClient.cs
using System.Net.Http.Json;
using System.Net.Http.Headers;
using System.Text.Json.Serialization;

namespace YourApp.Assistant;

// Adjust namespace and dependency-injection registration to your existing .NET project.
public sealed class AssistantCoordinatorClient(HttpClient httpClient)
{
    public Task<CoordinatorChatResponse> SendAsync(
        CoordinatorChatRequest request,
        CancellationToken cancellationToken = default) =>
        SendAsync(request, null, cancellationToken);

    // Forward the validated user's SSO access token. Do not put it in the JSON body,
    // log it, or persist it in conversation/approval storage.
    public async Task<CoordinatorChatResponse> SendAsync(
        CoordinatorChatRequest request,
        string? userAccessToken,
        CancellationToken cancellationToken = default)
    {
        using var message = new HttpRequestMessage(HttpMethod.Post, "/api/v1/assistant/chat")
        {
            Content = JsonContent.Create(request)
        };
        if (!string.IsNullOrWhiteSpace(userAccessToken))
        {
            message.Headers.Authorization = new AuthenticationHeaderValue("Bearer", userAccessToken);
        }

        using var response = await httpClient.SendAsync(message, cancellationToken);
        response.EnsureSuccessStatusCode();

        return await response.Content.ReadFromJsonAsync<CoordinatorChatResponse>(
                   cancellationToken: cancellationToken)
               ?? throw new InvalidOperationException("Coordinator returned an empty response.");
    }

    // These methods are for server-side use only. The internal API key must come from
    // backend configuration and must never be sent to browser/mobile clients.
    public async Task<CoordinatorApprovalDetails> GetApprovalAsync(
        Guid approvalId, string tenantId, string internalApiKey,
        CancellationToken cancellationToken = default)
    {
        using var message = new HttpRequestMessage(
            HttpMethod.Get,
            $"/api/v1/erp/approvals/{approvalId}?tenantId={Uri.EscapeDataString(tenantId)}");
        message.Headers.Add("X-API-Key", internalApiKey);
        using var response = await httpClient.SendAsync(message, cancellationToken);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<CoordinatorApprovalDetails>(
                   cancellationToken: cancellationToken)
               ?? throw new InvalidOperationException("Coordinator returned an empty approval response.");
    }

    public Task<CoordinatorApprovalActionResponse> ApproveAsync(
        Guid approvalId, CoordinatorApprovalAction action, string userAccessToken,
        string internalApiKey, CancellationToken cancellationToken = default) =>
        SendApprovalActionAsync($"/api/v1/erp/approvals/{approvalId}/approve", action,
            userAccessToken, internalApiKey, cancellationToken);

    public Task<CoordinatorApprovalActionResponse> RejectAsync(
        Guid approvalId, CoordinatorApprovalAction action, string userAccessToken,
        string internalApiKey, CancellationToken cancellationToken = default) =>
        SendApprovalActionAsync($"/api/v1/erp/approvals/{approvalId}/reject", action,
            userAccessToken, internalApiKey, cancellationToken);

    private async Task<CoordinatorApprovalActionResponse> SendApprovalActionAsync(
        string path, CoordinatorApprovalAction action, string userAccessToken,
        string internalApiKey, CancellationToken cancellationToken)
    {
        using var message = new HttpRequestMessage(HttpMethod.Post, path)
        {
            Content = JsonContent.Create(action)
        };
        message.Headers.Authorization = new AuthenticationHeaderValue("Bearer", userAccessToken);
        message.Headers.Add("X-API-Key", internalApiKey);
        using var response = await httpClient.SendAsync(message, cancellationToken);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<CoordinatorApprovalActionResponse>(
                   cancellationToken: cancellationToken)
               ?? throw new InvalidOperationException("Coordinator returned an empty approval action response.");
    }
}

public sealed record CoordinatorChatRequest(
    [property: JsonPropertyName("requestId")] Guid RequestId,
    [property: JsonPropertyName("conversationId")] Guid? ConversationId,
    [property: JsonPropertyName("messageId")] Guid? MessageId,
    [property: JsonPropertyName("appId")] string AppId,
    [property: JsonPropertyName("tenantId")] string TenantId,
    [property: JsonPropertyName("userId")] string UserId,
    [property: JsonPropertyName("prompt")] string Prompt,
    [property: JsonPropertyName("locale")] string Locale = "fa-IR");

public sealed record CoordinatorChatResponse(
    [property: JsonPropertyName("requestId")] Guid RequestId,
    [property: JsonPropertyName("conversationId")] Guid? ConversationId,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("answer")] string? Answer,
    [property: JsonPropertyName("selectedPath")] string? SelectedPath,
    [property: JsonPropertyName("sources")] List<Dictionary<string, object?>> Sources,
    [property: JsonPropertyName("message")] string? Message,
    [property: JsonPropertyName("approvalId")] Guid? ApprovalId = null,
    [property: JsonPropertyName("approvalExpiresAt")] string? ApprovalExpiresAt = null);


public sealed record CoordinatorApprovalAction(
    [property: JsonPropertyName("tenantId")] string TenantId,
    [property: JsonPropertyName("approverUserId")] string ApproverUserId,
    [property: JsonPropertyName("comment")] string? Comment = null);

public sealed record CoordinatorApprovalDetails(
    [property: JsonPropertyName("approvalId")] Guid ApprovalId,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("tenantId")] string TenantId,
    [property: JsonPropertyName("requesterUserId")] string RequesterUserId,
    [property: JsonPropertyName("conversationId")] Guid ConversationId,
    [property: JsonPropertyName("prompt")] string Prompt,
    [property: JsonPropertyName("toolName")] string ToolName,
    [property: JsonPropertyName("arguments")] Dictionary<string, object?> Arguments,
    [property: JsonPropertyName("createdAt")] string CreatedAt,
    [property: JsonPropertyName("expiresAt")] string ExpiresAt,
    [property: JsonPropertyName("approvedBy")] string? ApprovedBy,
    [property: JsonPropertyName("completedAt")] string? CompletedAt,
    [property: JsonPropertyName("comment")] string? Comment);

public sealed record CoordinatorApprovalActionResponse(
    [property: JsonPropertyName("approvalId")] Guid ApprovalId,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("completedAt")] string? CompletedAt = null,
    [property: JsonPropertyName("toolName")] string? ToolName = null,
    [property: JsonPropertyName("answer")] string? Answer = null,
    [property: JsonPropertyName("historyPersisted")] bool? HistoryPersisted = null);
